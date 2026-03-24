"""Budget-aware context packing for LLM consumption.

Operates on ``RetrievedDocument`` and ``ExpandedBlock`` — no Agno or framework imports.
Re-uses the existing text/citation helpers from ``knowledge.retrieval.utils``.

Step 6: Final pack — send 3–6 strong blocks to LLM.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from typing import Any, Dict, List

from src.core.models.retrieval import RetrievedDocument
from src.knowledge.retrieval.utils.reference_formatter import normalize_whitespace, truncate
from src.knowledge.retrieval.utils.citations import (
    classify_source_type,
    extract_parent_title,
)

log = logging.getLogger(__name__)

# ── Defaults (overridable via RetrievalPolicy) ───────────────────────────

_DEFAULT_MAX_REFS = 8
_DEFAULT_MAX_TOTAL_CHARS = 12_000
_DEFAULT_MAX_CHAR_PER_REF = 3000
_DEFAULT_MAX_REFS_PER_DOC = 3
_DEFAULT_MIN_RERANK_SCORE = -2.0

# Step 6 block-level defaults
_DEFAULT_MAX_BLOCKS = 6
_DEFAULT_MIN_BLOCKS = 3
_DEFAULT_MAX_BLOCK_CHARS = 4000
_DEFAULT_MAX_TOTAL_BLOCK_CHARS = 16_000


def _char_budget_for_rank(rank: int, base_budget: int) -> int:
    if rank < 3:
        return base_budget
    if rank < 6:
        return int(base_budget * 0.67)
    return int(base_budget * 0.33)


def _section_breadcrumb(meta: Dict[str, Any]) -> str:
    """Build a clean breadcrumb from section_path, without duplicating heading_path.

    section_path segments are structured as "Kind: value", e.g.:
      "Space: TECH", "Page: My Page", "Section: Heading1 > Heading2", "Attachment: file.pdf"

    When a "Section:" segment is present it already encodes the full heading hierarchy,
    so heading_path must NOT be appended afterward (that causes "A > B > A > B").
    Space/Page prefixes are skipped — they're too noisy for inline breadcrumbs.
    """
    parts: List[str] = []
    has_section_entry = False

    for seg in meta.get("section_path", []):
        if seg.startswith(("Space:", "Page:")):
            # Skip space/page prefix tags — redundant with doc title field
            continue
        if seg.startswith("Section:"):
            # Expand "Section: A > B > C" into individual path components
            tail = seg.split(":", 1)[-1].strip()
            parts.extend(c.strip() for c in tail.split(" > ") if c.strip())
            has_section_entry = True
        else:
            # Attachment:, Blog: etc. — keep the value portion
            tail = seg.split(":", 1)[-1].strip() if ":" in seg else seg
            if tail:
                parts.append(tail)

    # Only fall back to heading_path when no Section: was found in section_path
    if not has_section_entry:
        for h in meta.get("heading_path", []):
            if h and h not in parts:
                parts.append(h)

    if not parts and meta.get("heading"):
        parts.append(meta["heading"])

    return " > ".join(parts) if parts else ""


# ── Ref building ─────────────────────────────────────────────────────────


def build_ref(
    doc: RetrievedDocument,
    index: int,
    max_char_per_ref: int = _DEFAULT_MAX_CHAR_PER_REF,
) -> Dict[str, Any]:
    meta = doc.meta_data
    content = normalize_whitespace(doc.content)
    char_limit = _char_budget_for_rank(index, max_char_per_ref)
    content = truncate(content, char_limit)

    ref: Dict[str, Any] = {
        "ref": index + 1,
        "title": doc.name or meta.get("doc_title", ""),
        "type": classify_source_type(meta),
        "content": content,
        "url": meta.get("source_url", ""),
        "score": meta.get("rerank_score"),
        "kind": meta.get("chunk_kind", ""),
        "doc_id": meta.get("doc_id", ""),
        "chunk_position": meta.get("chunk_position", 0),
        "section_id": meta.get("section_id", ""),
    }
    section = _section_breadcrumb(meta)
    if section:
        ref["section"] = section
    parent = extract_parent_title(meta)
    if parent:
        ref["parent"] = parent
    return ref


# ── Block-level packing (Step 6) ────────────────────────────────────────


def pack_blocks(
    blocks: List[Any],  # List[ExpandedBlock]
    *,
    max_blocks: int = _DEFAULT_MAX_BLOCKS,
    min_blocks: int = _DEFAULT_MIN_BLOCKS,
    max_block_chars: int = _DEFAULT_MAX_BLOCK_CHARS,
    max_total_chars: int = _DEFAULT_MAX_TOTAL_BLOCK_CHARS,
) -> List[Dict[str, Any]]:
    """Pack expanded blocks into final LLM-ready refs.

    Targets 3–6 strong blocks within the total char budget.
    Each block is a self-contained context unit with title, section, url, content.
    """
    if not blocks:
        return []

    refs: List[Dict[str, Any]] = []
    total_chars = 0

    for i, block in enumerate(blocks):
        if len(refs) >= max_blocks:
            break

        content = normalize_whitespace(block.content)
        char_limit = _char_budget_for_rank(i, max_block_chars)
        content = truncate(content, char_limit)

        content_len = len(content)
        if total_chars + content_len > max_total_chars and len(refs) >= min_blocks:
            break

        ref: Dict[str, Any] = {
            "ref": i + 1,
            "title": block.source_label,
            "content": content,
            "url": block.source_url,
            "score": block.best_hit_score,
            "doc_id": block.doc_id,
            "section_id": block.section_id,
            "chunk_count": len(block.chunks),
        }
        refs.append(ref)
        total_chars += content_len

    log.debug(
        "Packed %d / %d blocks, total %d chars",
        len(refs), len(blocks), total_chars,
    )
    return refs


def blocks_to_documents(blocks: List[Any]) -> List[RetrievedDocument]:
    """Convert expanded blocks back to flat document list for citation building."""
    docs: list[RetrievedDocument] = []
    for block in blocks:
        docs.append(block.as_document())
    return docs


# ── Legacy ref-level packing ────────────────────────────────────────────


def pack_refs(
    docs: List[RetrievedDocument],
    *,
    max_refs: int = _DEFAULT_MAX_REFS,
    max_total_chars: int = _DEFAULT_MAX_TOTAL_CHARS,
    max_refs_per_doc: int = _DEFAULT_MAX_REFS_PER_DOC,
    max_char_per_ref: int = _DEFAULT_MAX_CHAR_PER_REF,
    min_rerank_score: float = _DEFAULT_MIN_RERANK_SCORE,
) -> List[Dict[str, Any]]:
    """Budget-aware packing: score gate → diversity cap → document-grouped assembly → char budget."""
    # 1. Score gate
    filtered = [d for d in docs if d.meta_data.get("rerank_score", 0.0) >= min_rerank_score]
    if not filtered:
        filtered = list(docs)

    # 2. Group by doc_id, ordered by best score in group
    doc_groups: dict[str, list[RetrievedDocument]] = OrderedDict()
    for d in filtered:
        did = d.meta_data.get("doc_id", "")
        doc_groups.setdefault(did, []).append(d)

    sorted_groups = sorted(
        doc_groups.items(),
        key=lambda kv: max(d.meta_data.get("rerank_score", 0.0) for d in kv[1]),
        reverse=True,
    )

    # 3. Flatten with diversity cap, chunks ordered by position within group
    diverse: list[RetrievedDocument] = []
    for _did, group in sorted_groups:
        group.sort(key=lambda d: d.meta_data.get("chunk_position", 0))
        count = 0
        for d in group:
            if count >= max_refs_per_doc:
                break
            diverse.append(d)
            count += 1

    # 4. Build refs within char budget
    refs: List[Dict[str, Any]] = []
    total_chars = 0
    for i, d in enumerate(diverse):
        if len(refs) >= max_refs:
            break
        r = build_ref(d, i, max_char_per_ref)
        ref_chars = len(r.get("content", ""))
        if total_chars + ref_chars > max_total_chars and refs:
            break
        refs.append(r)
        total_chars += ref_chars

    return refs


def format_docs_for_llm(docs: List[RetrievedDocument], **pack_kwargs: Any) -> str:
    """Serialize documents to JSON string for tool-call responses."""
    packed = pack_refs(docs, **pack_kwargs)
    return json.dumps(packed, ensure_ascii=False)
