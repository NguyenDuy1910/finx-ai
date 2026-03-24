from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, TYPE_CHECKING, runtime_checkable

from src.core.models.retrieval import RetrievedDocument
from src.knowledge.indexing.utils import models
from src.knowledge.retrieval.utils.expand_context import ContextExpander
from src.knowledge.retrieval.utils.reference_formatter import ReferenceFormatter
from src.providers.qdrant import QdrantClient

if TYPE_CHECKING:
    from sentence_transformers import SparseEncoder

log = logging.getLogger(__name__)


# ── lightweight protocols for injected dependencies ──────────────────────


@runtime_checkable
class DenseEmbedder(Protocol):
    def get_embedding(self, text: str) -> list[float]: ...


class RetrievalConfig(Protocol):
    collection_name: str
    dense_vector_name: str
    sparse_vector_name: str
    candidate_limit: int
    use_hybrid: bool
    max_content_chars: int
    expand_section_context: bool
    max_section_expansion: int
    expand_neighbor_window: int
    max_neighbor_expansion: int


class FilterBuilder(Protocol):
    def build(self, filters: dict[str, Any]) -> models.Filter | None: ...


# ── conversion helpers (exported via retrieval __init__) ─────────────────


def payload_to_document(
    payload: dict[str, Any],
    *,
    point_id: str | None = None,
) -> RetrievedDocument:
    """Convert a raw Qdrant payload dict into a ``RetrievedDocument``."""
    doc_title = (payload.get("doc_title") or "").strip()
    heading = (payload.get("heading") or "").strip()
    title_parts = [p for p in (doc_title, heading) if p]
    name = " > ".join(title_parts) if title_parts else "Untitled chunk"

    # Build rich content: primary text + summary for LLM context
    display_text = (payload.get("display_text") or "").strip()
    chunk_text = (payload.get("chunk_text") or "").strip()
    summary = (payload.get("summary") or "").strip()

    primary = display_text or chunk_text
    parts: list[str] = []
    if summary:
        parts.append(f"[Summary] {summary}")
    if primary:
        parts.append(primary)
    elif not summary:
        # fallback: use chunk_text even if empty display_text
        parts.append(chunk_text)

    content = "\n\n".join(parts)

    meta: dict[str, Any] = {
        "doc_id": payload.get("doc_id"),
        "chunk_id": payload.get("chunk_id"),
        "section_id": payload.get("section_id"),
        "source_system": payload.get("source_system"),
        "source_url": payload.get("source_url"),
        "chunk_kind": payload.get("chunk_kind"),
        "chunk_position": payload.get("chunk_position"),
        "total_chunks": payload.get("total_chunks"),
        "quality_score": payload.get("quality_score"),
        # Fields needed by grouper (_source_label) and expander (_merge_chunks_text)
        "doc_title": payload.get("doc_title"),
        "heading": payload.get("heading"),
        "heading_path": payload.get("heading_path"),
        "section_path": payload.get("section_path"),
        "external_id": payload.get("external_id"),
        # Fields needed by citations (images, files, attachments)
        "artifact_uri": payload.get("artifact_uri"),
        "mime_type": payload.get("mime_type"),
        "source_type": payload.get("source_type"),
        "parent_content_id": payload.get("parent_content_id"),
        "space_key": payload.get("space_key"),
        "attachment_id": payload.get("attachment_id"),
    }
    if point_id is not None:
        meta["point_id"] = point_id

    return RetrievedDocument(
        name=name,
        content=content,
        meta_data={k: v for k, v in meta.items() if v is not None},
    )


def scored_point_to_document(point: Any) -> RetrievedDocument:
    """Convert a Qdrant *ScoredPoint* (with ``.payload`` and ``.score``)."""
    payload: dict[str, Any] = getattr(point, "payload", {}) or {}
    doc = payload_to_document(payload, point_id=str(getattr(point, "id", "")))
    score = getattr(point, "score", None)
    if score is not None:
        doc.meta_data["qdrant_score"] = score
    return doc


# ── low-level Qdrant access layer ───────────────────────────────────────


class RetrievalStore:
    """Low-level Qdrant access layer. Only this class talks directly to Qdrant."""

    def __init__(
        self,
        *,
        client: QdrantClient,
        embedder: DenseEmbedder,
        config: RetrievalConfig,
        sparse_encoder: SparseEncoder | None = None,
    ) -> None:
        self.client = client
        self.embedder = embedder
        self.sparse_encoder = sparse_encoder
        self.config = config

    def search(
        self,
        *,
        query: str,
        limit: int,
        query_filter: models.Filter | None = None,
    ) -> list[Any]:
        query_embedding = self.embedder.get_embedding(query)

        if self.config.use_hybrid and self.sparse_encoder is not None:
            sparse_query = self.sparse_encoder.embed_query(query)
            response = self.client.query_points(
                collection_name=self.config.collection_name,
                prefetch=[
                    models.Prefetch(
                        query=query_embedding,
                        using=self.config.dense_vector_name,
                        limit=self.config.candidate_limit,
                        filter=query_filter,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_query.indices,
                            values=sparse_query.values,
                        ),
                        using=self.config.sparse_vector_name,
                        limit=self.config.candidate_limit,
                        filter=query_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
            return list(response.points)

        response = self.client.query_points(
            collection_name=self.config.collection_name,
            query=query_embedding,
            using=self.config.dense_vector_name,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return list(response.points)

    def get_section_points(self, *, section_id: str, limit: int) -> list[Any]:
        response = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="section_id",
                        match=models.MatchValue(value=section_id),
                    )
                ]
            ),
            with_payload=True,
            limit=limit,
        )
        return list(response[0])

    def get_neighbor_points(
        self,
        *,
        doc_id: str,
        chunk_position: int,
        window: int,
        limit: int,
    ) -> list[Any]:
        response = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id),
                    ),
                    models.FieldCondition(
                        key="chunk_position",
                        range=models.Range(
                            gte=chunk_position - window,
                            lte=chunk_position + window,
                        ),
                    ),
                ]
            ),
            with_payload=True,
            limit=limit,
        )
        return list(response[0])


# backward-compat alias used by ConfluenceKnowledge and expand_context
QdrantRetrievalStore = RetrievalStore


# ── high-level Agno-compatible retriever ─────────────────────────────────


class ConfluenceKnowledge:

    def __init__(
        self,
        *,
        store: RetrievalStore,
        filter_builder: FilterBuilder | None = None,
        expander: ContextExpander | None = None,
        formatter: ReferenceFormatter | None = None,
    ) -> None:
        self.store = store
        self.filter_builder = filter_builder
        self.expander = expander or ContextExpander(store)
        self.formatter = formatter or ReferenceFormatter(
            max_content_chars=store.config.max_content_chars
        )

    def search(
        self,
        query: str,
        agent: Optional[Any] = None,
        num_documents: int = 5,
        run_context: Optional[Any] = None,
        **kwargs: Any,
    ) -> Optional[list[dict[str, Any]]]:
        """Agno-compatible custom retriever method."""
        try:
            active_store = self._resolve_runtime_store(run_context)

            knowledge_filters = kwargs.get("knowledge_filters") or {}
            query_filter = (
                self.filter_builder.build(knowledge_filters)
                if self.filter_builder
                else None
            )

            base_points = active_store.search(
                query=query,
                limit=num_documents,
                query_filter=query_filter,
            )

            expanded = self.expander.expand(
                base_points,
                target_count=max(num_documents, len(base_points)),
            )

            return self.formatter.format_many(expanded, limit=num_documents)
        except Exception:
            log.exception("ConfluenceKnowledge search failed")
            return None

    def _resolve_runtime_store(
        self,
        run_context: Optional[Any],
    ) -> RetrievalStore:
        """Allow runtime override from Agno dependencies."""
        if run_context is None or not getattr(run_context, "dependencies", None):
            return self.store

        deps = run_context.dependencies

        runtime_store = deps.get("retrieval_store")
        if isinstance(runtime_store, RetrievalStore):
            return runtime_store

        runtime_config = deps.get("retrieval_config")
        if runtime_config is None:
            return self.store

        return RetrievalStore(
            client=self.store.client,
            embedder=self.store.embedder,
            sparse_encoder=self.store.sparse_encoder,
            config=runtime_config,
        )

    