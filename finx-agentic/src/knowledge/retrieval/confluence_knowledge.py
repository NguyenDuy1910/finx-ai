from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List

from agno.knowledge.document.base import Document

from .reranker import DocumentReranker

log = logging.getLogger("finx-agentic.confluence-knowledge")

_CHUNK_KINDS_TABLE = {"table_summary", "table_schema", "table_row_group", "schema_summary"}
_MAX_CHUNKS_PER_DOC = 3


@dataclass
class RetrievalMetrics:
    query: str = ""
    latency_embed_ms: float = 0
    latency_search_ms: float = 0
    latency_rerank_ms: float = 0
    latency_total_ms: float = 0
    candidates: int = 0
    after_dedup: int = 0
    final_count: int = 0
    filters_applied: list[str] = field(default_factory=list)


class ConfluenceKnowledge:
    """Qdrant-backed retrieval for chunked enterprise documents.

    Satisfies Agno KnowledgeProtocol: Agent(knowledge=ConfluenceKnowledge(...)).

    Pipeline: embed -> search -> deduplicate -> boost -> rerank -> expand -> package

    Hybrid search: when the collection has a named sparse vector ("sparse"),
    queries use prefetch(dense) + prefetch(sparse) with Reciprocal Rank Fusion.
    Otherwise falls back to dense-only search automatically.
    """

    def __init__(
        self,
        *,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        collection_name: str = "finx_knowledge",
        embedding_model: str = "text-embedding-3-small",
        reranker: DocumentReranker | None = None,
        top_k: int = 30,
        rerank_top_n: int = 8,
        min_score: float = 0.0,
        max_chunks_per_doc: int = _MAX_CHUNKS_PER_DOC,
        expand_context: bool = True,
    ) -> None:
        self._url = qdrant_url or os.environ.get("QDRANT_URL", "http://localhost:6333")
        self._api_key = qdrant_api_key or os.environ.get("QDRANT_API_KEY")
        self._collection = collection_name
        self._embedding_model = embedding_model
        self._reranker = reranker or DocumentReranker()
        self._top_k = top_k
        self._rerank_top_n = rerank_top_n
        self._min_score = min_score
        self._max_chunks_per_doc = max_chunks_per_doc
        self._expand_context = expand_context
        self._client: Any = None
        self._openai: Any = None
        self._has_sparse: bool | None = None  # lazy-detected

    def _get_client(self) -> Any:
        if self._client is None:
            from qdrant_client import AsyncQdrantClient
            self._client = AsyncQdrantClient(url=self._url, api_key=self._api_key)
        return self._client

    def _get_openai(self) -> Any:
        if self._openai is None:
            from openai import AsyncOpenAI
            self._openai = AsyncOpenAI()
        return self._openai

    async def _check_sparse_support(self) -> bool:
        """Detect whether the collection has a named sparse vector."""
        if self._has_sparse is not None:
            return self._has_sparse
        try:
            client = self._get_client()
            info = await client.get_collection(self._collection)
            vectors_config = info.config.params.vectors
            # Named vectors scenario: vectors_config is a dict
            if isinstance(vectors_config, dict) and "sparse" in vectors_config:
                self._has_sparse = True
            else:
                self._has_sparse = False
        except Exception:
            self._has_sparse = False
        log.info("Collection '%s' sparse vector support: %s", self._collection, self._has_sparse)
        return self._has_sparse

    # -- KnowledgeProtocol --

    def build_context(self, **kwargs: Any) -> str:
        return (
            "You have access to company knowledge from Confluence, Jira, and internal documents. "
            "Use search_knowledge to find policies, procedures, technical specs, business rules, "
            "and project documentation. Results include page IDs for fetching full content."
        )

    def get_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    async def aget_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    def retrieve(self, query: str, **kwargs: Any) -> List[Document]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.aretrieve(query, **kwargs)).result()
        return asyncio.run(self.aretrieve(query, **kwargs))

    async def aretrieve(self, query: str, **kwargs: Any) -> List[Document]:
        t0 = time.monotonic()
        metrics = RetrievalMetrics(query=query[:80])

        top_k: int = kwargs.get("top_k", self._top_k)
        rerank_top_n: int = kwargs.get("rerank_top_n", self._rerank_top_n)
        qdrant_filter = _build_filter(kwargs)
        if qdrant_filter:
            metrics.filters_applied = [c.key for c in (qdrant_filter.must or [])]

        # 1. Embed
        t1 = time.monotonic()
        try:
            vector = await self._embed(query)
        except Exception as exc:
            log.error("Embed failed for '%s': %s", query[:60], exc)
            return []
        metrics.latency_embed_ms = (time.monotonic() - t1) * 1000

        # 2. Search Qdrant (hybrid if sparse vectors available, else dense-only)
        t2 = time.monotonic()
        try:
            client = self._get_client()
            has_sparse = await self._check_sparse_support()

            if has_sparse:
                hits = await self._hybrid_search(client, vector, query, top_k, qdrant_filter)
            else:
                results = await client.query_points(
                    collection_name=self._collection,
                    query=vector,
                    limit=top_k,
                    query_filter=qdrant_filter,
                    with_payload=True,
                    score_threshold=self._min_score if self._min_score > 0 else None,
                )
                hits = results.points
        except Exception as exc:
            log.error("Qdrant search failed: %s", exc)
            return []
        metrics.latency_search_ms = (time.monotonic() - t2) * 1000
        metrics.candidates = len(hits)

        if not hits:
            log.debug("No hits for query=%r", query[:60])
            return []

        # 3. Deduplicate: limit chunks per doc_id
        hits = _deduplicate_by_doc(hits, self._max_chunks_per_doc)
        metrics.after_dedup = len(hits)

        # 4. Convert to Documents with metadata-aware score boost
        docs = [_hit_to_document(hit, query) for hit in hits]

        # 5. Rerank
        t3 = time.monotonic()
        reranked = self._reranker.rerank(query, docs, top_n=rerank_top_n)
        metrics.latency_rerank_ms = (time.monotonic() - t3) * 1000

        # 6. Expand context: fetch sibling chunks for thin results
        if self._expand_context and reranked:
            reranked = await self._expand_siblings(reranked, top_n=rerank_top_n)

        metrics.final_count = len(reranked)
        metrics.latency_total_ms = (time.monotonic() - t0) * 1000

        log.info(
            "Retrieval: %d candidates -> %d dedup -> %d final | "
            "embed=%.0fms search=%.0fms rerank=%.0fms total=%.0fms | filters=%s",
            metrics.candidates, metrics.after_dedup, metrics.final_count,
            metrics.latency_embed_ms, metrics.latency_search_ms,
            metrics.latency_rerank_ms, metrics.latency_total_ms,
            metrics.filters_applied or "none",
        )
        return reranked

    # -- Tool for Agno agent --

    async def _search_tool(self, query: str) -> str:
        """Search company knowledge base for relevant documents.

        Use when user asks about company policies, procedures, technical specs,
        business rules, or project documentation. Returns summaries with page IDs
        for fetching full content via confluence_get_page.
        """
        docs = await self.aretrieve(query)
        if not docs:
            return "No relevant company knowledge found for this query."

        parts: list[str] = []
        for i, doc in enumerate(docs, 1):
            meta = doc.meta_data or {}
            title = meta.get("doc_title", f"Document {i}")
            source_url = meta.get("source_url", "")
            external_id = meta.get("external_id", "")
            chunk_kind = meta.get("chunk_kind", "")
            score = meta.get("rerank_score")
            score_str = f" (score: {score:.3f})" if isinstance(score, (int, float)) else ""

            header = f"[{i}] {title}{score_str}"
            if chunk_kind:
                header += f" [{chunk_kind}]"
            if source_url:
                header += f"\nSource: {source_url}"
            if external_id:
                header += f"\nPage ID: {external_id}"
            parts.append(f"{header}\n{doc.content or ''}")

        return "\n\n---\n\n".join(parts)

    # -- Embedding --

    async def _embed(self, text: str) -> list[float]:
        client = self._get_openai()
        response = await client.embeddings.create(input=[text], model=self._embedding_model)
        return response.data[0].embedding

    # -- Hybrid search --

    async def _hybrid_search(
        self,
        client: Any,
        dense_vector: list[float],
        query_text: str,
        top_k: int,
        qdrant_filter: Any | None,
    ) -> list:
        """Prefetch dense + sparse, fuse with RRF, return merged hits."""
        from qdrant_client.models import (
            Fusion,
            FusionQuery,
            NamedVector,
            Prefetch,
        )

        # Build sparse vector from query text via simple term-frequency
        sparse = _text_to_sparse_vector(query_text)

        prefetch_dense = Prefetch(
            query=NamedVector(name="dense", vector=dense_vector),
            limit=top_k,
            filter=qdrant_filter,
        )
        prefetch_sparse = Prefetch(
            query=NamedVector(name="sparse", vector=sparse),
            limit=top_k,
            filter=qdrant_filter,
        )

        results = await client.query_points(
            collection_name=self._collection,
            prefetch=[prefetch_dense, prefetch_sparse],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return results.points

    # -- Sibling expansion --

    async def _expand_siblings(self, docs: list[Document], top_n: int) -> list[Document]:
        expanded: list[Document] = []
        seen_chunk_ids: set[str] = set()

        for doc in docs:
            meta = doc.meta_data or {}
            expanded.append(doc)
            seen_chunk_ids.add(meta.get("chunk_id", ""))

            content_len = len(doc.content or "")
            if content_len > 300:
                continue

            doc_id = meta.get("doc_id", "")
            section_id = meta.get("section_id", "")
            if not doc_id or not section_id:
                continue

            try:
                siblings = await self._fetch_siblings(doc_id, section_id)
                for sib in siblings:
                    sib_meta = sib.meta_data or {}
                    if sib_meta.get("chunk_id") not in seen_chunk_ids:
                        seen_chunk_ids.add(sib_meta.get("chunk_id", ""))
                        expanded.append(sib)
            except Exception:
                pass

        return expanded[:top_n + 2]

    async def _fetch_siblings(self, doc_id: str, section_id: str) -> list[Document]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        client = self._get_client()
        results = await client.scroll(
            collection_name=self._collection,
            scroll_filter=Filter(must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="section_id", match=MatchValue(value=section_id)),
            ]),
            limit=3,
            with_payload=True,
            with_vectors=False,
        )
        return [_scroll_hit_to_document(point) for point in results[0]]


# -- Qdrant hit -> Agno Document --

def _hit_to_document(hit: Any, query: str = "") -> Document:
    p: dict = hit.payload or {}
    content, meta = _payload_to_content_and_meta(p, query)
    meta["qdrant_score"] = float(hit.score) if hit.score else 0.0
    meta["point_id"] = str(hit.id)

    # Metadata-aware score boost
    boost = 0.0
    if query and meta.get("doc_title"):
        q_lower = query.lower()
        t_lower = meta["doc_title"].lower()
        if q_lower in t_lower or t_lower in q_lower:
            boost += 0.05
    if (meta.get("quality_score") or 0) > 0.7:
        boost += 0.02
    if meta.get("chunk_kind") in ("intro", "doc_header", "section"):
        boost += 0.01
    meta["boosted_score"] = meta["qdrant_score"] + boost

    return Document(
        name=meta.get("doc_title") or meta.get("external_id") or str(hit.id),
        content=content,
        meta_data=meta,
    )


def _scroll_hit_to_document(point: Any) -> Document:
    p: dict = point.payload or {}
    content, meta = _payload_to_content_and_meta(p)
    meta["qdrant_score"] = 0.0
    meta["boosted_score"] = 0.0
    meta["point_id"] = str(point.id)
    return Document(
        name=meta.get("doc_title") or meta.get("external_id") or str(point.id),
        content=content,
        meta_data=meta,
    )


def _payload_to_content_and_meta(p: dict, query: str = "") -> tuple[str, dict]:
    doc_title = p.get("doc_title", "")
    display_text = p.get("display_text", "") or p.get("chunk_text", "")
    heading = p.get("heading", "")
    heading_path: list[str] = p.get("heading_path", [])
    summary = p.get("summary", "")
    chunk_kind = p.get("chunk_kind", "")
    table_headers: list[str] = p.get("table_headers", [])

    content_parts: list[str] = []
    if doc_title:
        loc = doc_title
        if heading_path:
            loc += " > " + " > ".join(heading_path)
        elif heading:
            loc += " > " + heading
        content_parts.append(loc)
    if display_text:
        content_parts.append(display_text)
    if chunk_kind in _CHUNK_KINDS_TABLE and table_headers:
        content_parts.append(f"Columns: {', '.join(table_headers)}")
    if summary and len(summary) < 200 and summary != display_text:
        content_parts.append(f"Summary: {summary}")

    content = "\n\n".join(content_parts)

    meta = {
        "doc_title": doc_title,
        "source_url": p.get("source_url", ""),
        "source_system": p.get("source_system", ""),
        "external_id": p.get("external_id", ""),
        "doc_id": p.get("doc_id", ""),
        "chunk_id": p.get("chunk_id", ""),
        "section_id": p.get("section_id", ""),
        "chunk_kind": chunk_kind,
        "doc_type": p.get("doc_type", ""),
        "source_type": p.get("source_type", ""),
        "content_type": p.get("content_type", ""),
        "language": p.get("language", ""),
        "space_key": p.get("space_key", ""),
        "domains": p.get("domains", []),
        "heading": heading,
        "heading_path": heading_path,
        "section_path": p.get("section_path", []),
        "keywords": p.get("keywords", []),
        "quality_score": p.get("quality_score", 0.0),
        "chunk_position": p.get("chunk_position", 0),
        "total_chunks": p.get("total_chunks", 0),
        "parent_content_id": p.get("parent_content_id", ""),
        "table_headers": table_headers,
        # Artifact metadata for inline image/file rendering
        "artifact_uri": p.get("artifact_uri", ""),
        "mime_type": p.get("mime_type", ""),
        "attachment_id": p.get("attachment_id", ""),
    }
    return content, meta


# -- Deduplication --

def _deduplicate_by_doc(hits: list, max_per_doc: int) -> list:
    doc_counts: dict[str, int] = {}
    result = []
    for hit in hits:
        doc_id = (hit.payload or {}).get("doc_id", str(hit.id))
        count = doc_counts.get(doc_id, 0)
        if count < max_per_doc:
            result.append(hit)
            doc_counts[doc_id] = count + 1
    return result


# -- Filter builder --

def _build_filter(kwargs: dict) -> Any | None:
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range
        conditions: list[Any] = []

        conditions.append(FieldCondition(key="is_deleted", match=MatchValue(value=False)))

        if language := kwargs.get("language"):
            conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))
        if domain := kwargs.get("domain"):
            conditions.append(FieldCondition(key="domains", match=MatchValue(value=domain)))
        if doc_type := kwargs.get("document_type"):
            conditions.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))
        if source_type := kwargs.get("source_type"):
            conditions.append(FieldCondition(key="source_type", match=MatchValue(value=source_type)))
        if content_type := kwargs.get("content_type"):
            conditions.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))
        if chunk_kind := kwargs.get("chunk_kind"):
            conditions.append(FieldCondition(key="chunk_kind", match=MatchValue(value=chunk_kind)))
        if space_key := kwargs.get("space_key"):
            conditions.append(FieldCondition(key="space_key", match=MatchValue(value=space_key)))
        if source_system := kwargs.get("source_system"):
            conditions.append(FieldCondition(key="source_system", match=MatchValue(value=source_system)))
        if min_quality := kwargs.get("min_quality"):
            conditions.append(FieldCondition(key="quality_score", range=Range(gte=float(min_quality))))

        return Filter(must=conditions) if conditions else None
    except Exception:
        return None


# -- Sparse vector helper --

def _text_to_sparse_vector(text: str) -> Any:
    """Build a simple term-frequency sparse vector from raw text.

    Hashes tokens to integer indices via SHA-256, compatible with
    Qdrant SparseVector.  Lightweight client-side BM25-ish
    representation; the sparse index in Qdrant handles the rest.
    """
    from qdrant_client.models import SparseVector

    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return SparseVector(indices=[0], values=[1.0])

    tf: dict[int, float] = {}
    for token in tokens:
        idx = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16)
        tf[idx] = tf.get(idx, 0.0) + 1.0

    indices = sorted(tf.keys())
    values = [tf[i] for i in indices]
    return SparseVector(indices=indices, values=values)
