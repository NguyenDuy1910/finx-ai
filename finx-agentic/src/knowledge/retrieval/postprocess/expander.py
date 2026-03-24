"""Step 4 — expand source groups into rich context blocks.

For each kept source group:
  • load parent section (heading/intro) for context
  • add sibling chunks / nearby rows
  • include title + section breadcrumb + source url in content

Also retains the original per-document expansion for backward compat.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, List, Set

from src.core.models.retrieval import RetrievedDocument
from src.providers.qdrant import get_qdrant_client
from src.knowledge.retrieval.postprocess.grouper import SourceGroup

log = logging.getLogger(__name__)

_CHUNK_KINDS_TABLE = frozenset(
    {"table_summary", "table_schema", "table_row_group", "schema_summary"}
)
_EXPANSION_THRESHOLD = 600  # chars


# ── Expanded block dataclass ────────────────────────────────────────────


@dataclass
class ExpandedBlock:
    """A self-contained context block ready for reranking."""

    source_label: str
    source_url: str
    doc_id: str
    section_id: str
    content: str  # merged text of all chunks in this block
    chunks: List[RetrievedDocument] = field(default_factory=list)
    best_hit_score: float = 0.0

    def as_document(self) -> RetrievedDocument:
        """Collapse the block into a single ``RetrievedDocument``."""
        meta = dict(self.chunks[0].meta_data) if self.chunks else {}
        meta["block_chunk_count"] = len(self.chunks)
        meta["block_source_label"] = self.source_label
        return RetrievedDocument(
            name=self.source_label,
            content=self.content,
            meta_data=meta,
        )


# ── Group-level expansion (Step 4) ──────────────────────────────────────


async def expand_groups(
    groups: List[SourceGroup],
    collection_name: str,
    *,
    policy: str = "standard",
    max_blocks: int = 8,
) -> List[ExpandedBlock]:
    """Expand each source group into a rich context block.

    For each group:
      1. Fetch parent section header / intro chunk
      2. Fetch sibling chunks / nearby rows
      3. Merge into a single coherent text with title + section + url
    """
    if policy == "skip" or not groups:
        return [_group_to_block_passthrough(g) for g in groups[:max_blocks]]

    tasks: list[tuple[int, SourceGroup, Any]] = []
    window = 2 if policy == "standard" else 3

    for i, group in enumerate(groups[:max_blocks]):
        doc_id = group.doc_id
        if not doc_id:
            continue
        best = group.best_hit
        chunk_kind = best.meta_data.get("chunk_kind", "")

        if chunk_kind in _CHUNK_KINDS_TABLE:
            tasks.append((i, group, _fetch_table_context(
                collection_name, doc_id, chunk_kind,
                best.meta_data.get("chunk_position", 0),
            )))
        elif group.section_id:
            tasks.append((i, group, _fetch_siblings(
                collection_name, doc_id, group.section_id,
            )))
        else:
            pos = best.meta_data.get("chunk_position", 0)
            tasks.append((i, group, _fetch_position_window(
                collection_name, doc_id, pos, window=window,
            )))

    # Also fetch parent section headers for richer context
    parent_tasks: list[tuple[int, SourceGroup, Any]] = []
    for i, group in enumerate(groups[:max_blocks]):
        doc_id = group.doc_id
        if not doc_id:
            continue
        parent_tasks.append((i, group, _fetch_parent_section(
            collection_name, doc_id,
        )))

    # Run all expansion + parent tasks in parallel
    sibling_results: dict[int, list[RetrievedDocument]] = {}
    parent_results: dict[int, list[RetrievedDocument]] = {}

    all_coros = [t for _, _, t in tasks] + [t for _, _, t in parent_tasks]
    if all_coros:
        raw = await asyncio.gather(*all_coros, return_exceptions=True)
        n_sibling = len(tasks)
        for idx_in_tasks, result in enumerate(raw[:n_sibling]):
            group_idx = tasks[idx_in_tasks][0]
            if isinstance(result, BaseException):
                log.debug("Expansion task failed for group %d: %s", group_idx, result)
            else:
                sibling_results[group_idx] = result
        for idx_in_tasks, result in enumerate(raw[n_sibling:]):
            group_idx = parent_tasks[idx_in_tasks][0]
            if isinstance(result, BaseException):
                log.debug("Parent fetch failed for group %d: %s", group_idx, result)
            else:
                parent_results[group_idx] = result

    # Build expanded blocks
    blocks: list[ExpandedBlock] = []
    for i, group in enumerate(groups[:max_blocks]):
        siblings = sibling_results.get(i, [])
        parents = parent_results.get(i, [])
        block = _build_block(group, siblings, parents)
        blocks.append(block)

    log.debug("Expander: %d groups → %d blocks", len(groups), len(blocks))
    return blocks


# ── Legacy per-document expansion (backward compat) ─────────────────────


async def expand(
    docs: List[RetrievedDocument],
    collection_name: str,
    *,
    top_n: int = 8,
    policy: str = "standard",
) -> List[RetrievedDocument]:
    """Expand context around *docs* by fetching siblings from Qdrant.

    Returns up to ``top_n + 4`` documents.
    ``policy`` is ``"standard"`` | ``"aggressive"`` | ``"skip"``.
    """
    if policy == "skip" or not docs:
        return docs

    expanded: list[RetrievedDocument] = []
    seen: Set[str] = set()
    tasks: list[tuple[int, Any]] = []
    threshold = _EXPANSION_THRESHOLD if policy == "standard" else int(_EXPANSION_THRESHOLD * 1.5)

    for doc in docs:
        meta = doc.meta_data
        idx = len(expanded)
        expanded.append(doc)
        seen.add(meta.get("chunk_id", ""))

        doc_id = meta.get("doc_id", "")
        if not doc_id:
            continue

        chunk_kind = meta.get("chunk_kind", "")
        chunk_position: int = meta.get("chunk_position", 0)
        section_id = meta.get("section_id", "")
        content_len = len(doc.content)

        # Table-kind expansion (always)
        if chunk_kind in _CHUNK_KINDS_TABLE or chunk_kind == "table_row_group":
            tasks.append((idx, _fetch_table_context(collection_name, doc_id, chunk_kind, chunk_position)))
            continue

        # Length-based expansion
        if content_len > threshold:
            continue

        if section_id:
            tasks.append((idx, _fetch_siblings(collection_name, doc_id, section_id)))
        else:
            tasks.append((idx, _fetch_position_window(collection_name, doc_id, chunk_position, window=2)))

    # Run expansion tasks in parallel
    if tasks:
        coros = [t for _, t in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for (_, _), result in zip(tasks, results):
            if isinstance(result, BaseException):
                log.debug("Expansion task failed: %s", result)
                continue
            for sib in result:
                sib_id = sib.meta_data.get("chunk_id", "")
                if sib_id not in seen:
                    seen.add(sib_id)
                    expanded.append(sib)

    return expanded[: top_n + 4]


# ── Block construction helpers ───────────────────────────────────────────


def _group_to_block_passthrough(group: SourceGroup) -> ExpandedBlock:
    """Wrap a group as a block without fetching extra context."""
    chunks = sorted(group.hits, key=lambda d: d.meta_data.get("chunk_position", 0))
    best = group.best_hit
    meta = best.meta_data
    return ExpandedBlock(
        source_label=group.source_label,
        source_url=meta.get("source_url", ""),
        doc_id=group.doc_id,
        section_id=group.section_id,
        content=_merge_chunks_text(chunks, group.source_label, meta.get("source_url", "")),
        chunks=chunks,
        best_hit_score=group.best_score,
    )


def _build_block(
    group: SourceGroup,
    siblings: list[RetrievedDocument],
    parents: list[RetrievedDocument],
) -> ExpandedBlock:
    """Merge group hits + expanded siblings + parent header into one block."""
    best = group.best_hit
    meta = best.meta_data
    source_url = meta.get("source_url", "")

    # Collect all unique chunks, ordered by position
    seen: set[str] = set()
    all_chunks: list[RetrievedDocument] = []

    # Parent sections first (for context framing)
    for p in parents:
        cid = p.meta_data.get("chunk_id", "")
        if cid and cid not in seen:
            seen.add(cid)
            all_chunks.append(p)

    # Original hits
    for h in group.hits:
        cid = h.meta_data.get("chunk_id", "")
        if cid and cid not in seen:
            seen.add(cid)
            all_chunks.append(h)
        elif not cid:
            all_chunks.append(h)

    # Sibling/expanded chunks
    for s in siblings:
        cid = s.meta_data.get("chunk_id", "")
        if cid and cid not in seen:
            seen.add(cid)
            all_chunks.append(s)

    # Sort by chunk_position for reading coherence
    all_chunks.sort(key=lambda d: d.meta_data.get("chunk_position", 0))

    return ExpandedBlock(
        source_label=group.source_label,
        source_url=source_url,
        doc_id=group.doc_id,
        section_id=group.section_id,
        content=_merge_chunks_text(all_chunks, group.source_label, source_url),
        chunks=all_chunks,
        best_hit_score=group.best_score,
    )


def _merge_chunks_text(
    chunks: list[RetrievedDocument],
    source_label: str,
    source_url: str,
) -> str:
    """Merge chunk texts into a single LLM-ready evidence block.

    Structure:
      Source: ...
      Section: ...   (clean breadcrumb, no duplication)
      URL: ...

      [body text, deduplicated, in chunk-position order]
    """
    import hashlib as _hashlib

    parts: list[str] = []

    # --- Header line -------------------------------------------------------
    header_parts: list[str] = []
    if source_label:
        header_parts.append(f"Source: {source_label}")

    # Section breadcrumb: use first chunk that has a section_path or heading_path
    _INTRO_KINDS = frozenset({"intro", "blog_intro", "doc_header"})
    breadcrumb = ""
    for c in chunks:
        m = c.meta_data
        # Skip introductory framing chunks for breadcrumb — they represent the
        # document root, not the specific section we matched against
        if m.get("chunk_kind", "") in _INTRO_KINDS:
            continue
        sp = m.get("section_path", [])
        hp = m.get("heading_path", [])
        if sp or hp:
            # Reuse the breadcrumb logic consistent with context_packer
            crumb_parts: list[str] = []
            has_section = False
            for seg in sp:
                if seg.startswith(("Space:", "Page:")):
                    continue
                if seg.startswith("Section:"):
                    tail = seg.split(":", 1)[-1].strip()
                    crumb_parts.extend(c2.strip() for c2 in tail.split(" > ") if c2.strip())
                    has_section = True
                else:
                    tail = seg.split(":", 1)[-1].strip() if ":" in seg else seg
                    if tail:
                        crumb_parts.append(tail)
            if not has_section:
                for h in hp:
                    if h and h not in crumb_parts:
                        crumb_parts.append(h)
            breadcrumb = " > ".join(crumb_parts)
            break

    if breadcrumb:
        header_parts.append(f"Section: {breadcrumb}")
    if source_url:
        header_parts.append(f"URL: {source_url}")

    if header_parts:
        parts.append("\n".join(header_parts))

    # --- Body: deduplicated chunk text, position-ordered --------------------
    seen_text: set[str] = set()
    for chunk in chunks:
        text = (chunk.content or "").strip()
        if not text:
            continue
        # Use a stable hash (first 100 chars via sha256) to deduplicate
        text_key = _hashlib.sha256(text[:100].encode()).hexdigest()[:16]
        if text_key in seen_text:
            continue
        seen_text.add(text_key)
        parts.append(text)

    return "\n\n".join(parts)


async def _fetch_parent_section(
    collection: str, doc_id: str
) -> List[RetrievedDocument]:
    """Fetch intro / header chunks for the document (parent context framing).

    Fetches only structural intro/header kinds — not 'section_title' which
    does not exist as a ChunkKind in this codebase.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    client = get_qdrant_client()
    results = await client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="is_deleted", match=MatchValue(value=False)),
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="chunk_kind", match=MatchAny(any=[
                "intro", "blog_intro", "doc_header",
            ])),
        ]),
        limit=2,
        with_payload=True,
        with_vectors=False,
    )
    return [_scroll_to_doc(p) for p in results[0]]


# ── internal scroll helpers ──────────────────────────────────────────────


def _scroll_to_doc(point: Any) -> RetrievedDocument:
    """Convert a raw Qdrant scroll point to ``RetrievedDocument``."""
    from src.knowledge.retrieval.confluence_knowledge import payload_to_document
    return payload_to_document(point.payload or {}, point_id=str(point.id))


async def _fetch_siblings(
    collection: str, doc_id: str, section_id: str
) -> List[RetrievedDocument]:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = get_qdrant_client()
    results = await client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="section_id", match=MatchValue(value=section_id)),
        ]),
        limit=3,
        with_payload=True,
        with_vectors=False,
    )
    return [_scroll_to_doc(p) for p in results[0]]


async def _fetch_position_window(
    collection: str, doc_id: str, chunk_position: int, window: int = 2
) -> List[RetrievedDocument]:
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    client = get_qdrant_client()
    results = await client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="is_deleted", match=MatchValue(value=False)),
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(
                key="chunk_position",
                range=Range(
                    gte=max(0, chunk_position - window),
                    lte=chunk_position + window,
                ),
            ),
        ]),
        limit=window * 2 + 1,
        with_payload=True,
        with_vectors=False,
    )
    return [_scroll_to_doc(p) for p in results[0]]


async def _fetch_by_chunk_kinds(
    collection: str, doc_id: str, kinds: list[str], limit: int = 5
) -> List[RetrievedDocument]:
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    client = get_qdrant_client()
    results = await client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="is_deleted", match=MatchValue(value=False)),
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="chunk_kind", match=MatchAny(any=kinds)),
        ]),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [_scroll_to_doc(p) for p in results[0]]


async def _fetch_table_context(
    collection: str, doc_id: str, chunk_kind: str, chunk_position: int
) -> List[RetrievedDocument]:
    results: list[RetrievedDocument] = []
    seen: set[str] = set()

    def _add(docs: list[RetrievedDocument]) -> None:
        for d in docs:
            cid = d.meta_data.get("chunk_id", "")
            if cid not in seen:
                seen.add(cid)
                results.append(d)

    if chunk_kind == "table_row_group":
        structural = await _fetch_by_chunk_kinds(
            collection, doc_id,
            ["table_schema", "table_summary", "schema_summary"], limit=3,
        )
        _add(structural)
        nearby = await _fetch_position_window(collection, doc_id, chunk_position, window=2)
        _add(nearby)
    elif chunk_kind in ("table_schema", "schema_summary"):
        nearby = await _fetch_position_window(collection, doc_id, chunk_position, window=3)
        _add(nearby)
    else:
        nearby = await _fetch_position_window(collection, doc_id, chunk_position, window=2)
        _add(nearby)

    return results


# ── Tool-level expansion helpers (used by on-demand tools) ───────────────


async def expand_document_context(
    collection_name: str,
    doc_id: str,
    chunk_position: int | None = None,
    section_id: str | None = None,
    window: int = 2,
    limit: int = 6,
) -> List[RetrievedDocument]:
    """Fetch surrounding context for a known document anchor."""
    seen: set[str] = set()
    results: list[RetrievedDocument] = []

    try:
        if section_id:
            docs = await _fetch_siblings(collection_name, doc_id, section_id)
        elif chunk_position is not None:
            docs = await _fetch_position_window(collection_name, doc_id, chunk_position, window=window)
        else:
            from qdrant_client.models import FieldCondition, Filter, MatchValue
            client = get_qdrant_client()
            raw = await client.scroll(
                collection_name=collection_name,
                scroll_filter=Filter(must=[
                    FieldCondition(key="is_deleted", match=MatchValue(value=False)),
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                ]),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            docs = [_scroll_to_doc(p) for p in raw[0]]

        for d in docs:
            cid = d.meta_data.get("chunk_id", "")
            if cid not in seen:
                seen.add(cid)
                results.append(d)
            if len(results) >= limit:
                break
    except Exception:
        pass

    return results
