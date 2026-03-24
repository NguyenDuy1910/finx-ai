from __future__ import annotations

# ── Implemented modules ──────────────────────────────────────────────────
from src.knowledge.retrieval.vector_knowledge import VectorKnowledge, SearchParams
from src.knowledge.retrieval.filters import build_qdrant_filter, build_doc_scope_filter, build_search_params_filter

# ── Forward imports: guarded until the modules are created ───────────────
try:
    from src.knowledge.retrieval.pipeline import RetrievalPipeline
    from src.knowledge.retrieval.tools import KnowledgeTools
    from src.knowledge.retrieval.policy import RetrievalPolicy
    from src.knowledge.retrieval.query_analyzer import QueryAnalyzer, QueryAnalysis
except ImportError:  # modules not yet implemented
    RetrievalPipeline = None  # type: ignore[assignment,misc]
    KnowledgeTools = None  # type: ignore[assignment,misc]
    RetrievalPolicy = None  # type: ignore[assignment,misc]
    QueryAnalyzer = None  # type: ignore[assignment,misc]
    QueryAnalysis = None  # type: ignore[assignment,misc]

# ── Stable imports: these modules exist ──────────────────────────────────
from src.knowledge.retrieval.confluence_knowledge import (
    payload_to_document,
    scored_point_to_document,
)
from src.knowledge.retrieval.utils.citations import (
    CITATIONS_STATE_KEY,
    accumulate_citations,
    build_full_citation,
)
from src.knowledge.retrieval.postprocess.context_packer import (
    format_docs_for_llm,
    pack_refs,
)

__all__ = [
    "RetrievalPipeline",
    "VectorKnowledge",
    "SearchParams",
    "KnowledgeTools",
    "RetrievalPolicy",
    "QueryAnalyzer",
    "QueryAnalysis",
    "build_qdrant_filter",
    "build_doc_scope_filter",
    "build_search_params_filter",
    "payload_to_document",
    "scored_point_to_document",
    "CITATIONS_STATE_KEY",
    "accumulate_citations",
    "build_full_citation",
    "format_docs_for_llm",
    "pack_refs",
]

from datetime import datetime
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator
from qdrant_client import models as qmodels




def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _compact_str(value: str | None) -> str:
    return (value or "").strip()



class AccessContext(BaseModel):
    """
    Security scope for retrieval.

    Always enforce this in the retriever before returning any chunk to the agent.
    """

    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    reader_ids: list[str] = Field(default_factory=list)
    space_keys: list[str] = Field(default_factory=list)
    is_admin: bool = False

    @field_validator("reader_ids", "space_keys", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return [str(v) for v in _as_list(value) if v is not None and str(v).strip()]



class PayloadFilters(BaseModel):
    """
    Filterable business fields from your Qdrant payload.

    These are safe for retrieval scoping.
    Do NOT put tenant / ACL / soft-delete here; those belong to AccessContext.
    """

    model_config = ConfigDict(extra="ignore")

    source_system: list[str] = Field(default_factory=list)
    doc_type: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    project_key: list[str] = Field(default_factory=list)
    space_key: list[str] = Field(default_factory=list)
    ticket_status: list[str] = Field(default_factory=list)
    ticket_type: list[str] = Field(default_factory=list)
    source_type: list[str] = Field(default_factory=list)
    content_type: list[str] = Field(default_factory=list)
    chunk_kind: list[str] = Field(default_factory=list)
    language: list[str] = Field(default_factory=list)

    doc_id: list[str] = Field(default_factory=list)
    section_id: list[str] = Field(default_factory=list)
    external_id: list[str] = Field(default_factory=list)
    parent_content_id: list[str] = Field(default_factory=list)
    attachment_id: list[str] = Field(default_factory=list)
    comment_id: list[str] = Field(default_factory=list)
    sheet_name: list[str] = Field(default_factory=list)

    is_public: bool | None = None
    min_quality_score: float | None = None

    @field_validator(
        "source_system",
        "doc_type",
        "domains",
        "project_key",
        "space_key",
        "ticket_status",
        "ticket_type",
        "source_type",
        "content_type",
        "chunk_kind",
        "language",
        "doc_id",
        "section_id",
        "external_id",
        "parent_content_id",
        "attachment_id",
        "comment_id",
        "sheet_name",
        mode="before",
    )
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return [str(v) for v in _as_list(value) if v is not None and str(v).strip()]

    def has_filters(self) -> bool:
        data = self.model_dump(exclude_none=True)
        for _, value in data.items():
            if isinstance(value, list) and value:
                return True
            if not isinstance(value, list):
                return True
        return False


class RetrievalRequest(BaseModel):
    """
    Full retrieval request passed into your retriever.
    """

    model_config = ConfigDict(extra="ignore")

    query: str
    access: AccessContext
    filters: PayloadFilters = Field(default_factory=PayloadFilters)

    top_k: int = 6
    candidate_limit: int = 30
    use_hybrid: bool = True
    rerank_top_k: int | None = 10

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value

    @field_validator("top_k")
    @classmethod
    def _validate_top_k(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("top_k must be > 0")
        return value

    @field_validator("candidate_limit")
    @classmethod
    def _validate_candidate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("candidate_limit must be > 0")
        return value


class ChunkPayload(BaseModel):
    """
    Typed representation of your Qdrant payload.

    This model matches your current payload structure closely.
    """

    model_config = ConfigDict(extra="ignore")

    # Identity
    tenant_id: str
    doc_id: str
    chunk_id: str
    section_id: str | None = None
    external_id: str | None = None
    source_url: str | None = None

    # Content
    source_system: str | None = None
    doc_title: str | None = None
    heading: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    chunk_kind: str | None = None
    chunk_text: str = ""
    display_text: str = ""

    # Classification
    language: str | None = None
    doc_type: str | None = None
    domains: list[str] = Field(default_factory=list)
    project_key: str | None = None
    space_key: str | None = None
    ticket_status: str | None = None
    ticket_type: str | None = None
    source_type: str | None = None
    content_type: str | None = None

    # Content graph
    attachment_id: str | None = None
    comment_id: str | None = None
    parent_content_id: str | None = None
    mime_type: str | None = None
    artifact_uri: str | None = None
    body_representation: str | None = None
    section_path: list[str] = Field(default_factory=list)

    # Enrichment
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)

    # Timestamps
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    ingested_at: datetime | None = None

    # Change detection
    doc_hash: str | None = None
    section_hash: str | None = None
    chunk_hash: str | None = None

    # Embedding metadata
    embedding_model: str | None = None
    embedding_version: str | None = None

    # ACL
    acl_readers: list[str] = Field(default_factory=list)
    acl_spaces: list[str] = Field(default_factory=list)
    is_public: bool = False

    # Soft delete
    is_deleted: bool = False

    # Quality
    quality_score: float | None = None
    chunk_position: int | None = None
    total_chunks: int | None = None

    # Table-specific
    table_headers: list[str] = Field(default_factory=list)
    table_row_count: int | None = None

    # Document location
    page_range: Any | None = None
    sheet_name: str | None = None
    page_numbers: list[int] = Field(default_factory=list)

    # Terminology
    acronym_expansions: dict[str, str] = Field(default_factory=dict)

    # Enhanced
    pipeline_version: str | None = None
    parent_chunk_id: str | None = None
    entities: list[Any] = Field(default_factory=list)

    @field_validator(
        "heading_path",
        "domains",
        "section_path",
        "keywords",
        "acl_readers",
        "acl_spaces",
        "table_headers",
        "page_numbers",
        "entities",
        mode="before",
    )
    @classmethod
    def _normalize_any_list(cls, value: Any) -> list[Any]:
        return _as_list(value)

    @field_validator("acronym_expansions", mode="before")
    @classmethod
    def _normalize_dict(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        raise ValueError("acronym_expansions must be a dict or None")

    def best_content(self) -> str:
        return _compact_str(self.display_text) or _compact_str(self.chunk_text) or _compact_str(self.summary)

    def path_text(self) -> str:
        if self.section_path:
            return " > ".join([str(p).strip() for p in self.section_path if str(p).strip()])
        if self.heading_path:
            return " > ".join([str(p).strip() for p in self.heading_path if str(p).strip()])
        return ""

    def title_text(self) -> str:
        parts: list[str] = []
        if _compact_str(self.doc_title):
            parts.append(_compact_str(self.doc_title))
        if _compact_str(self.heading):
            parts.append(_compact_str(self.heading))
        if parts:
            return " > ".join(parts)
        if self.path_text():
            return self.path_text()
        return "Untitled chunk"

    def location_text(self) -> str:
        parts: list[str] = []

        if self.page_range:
            parts.append(f"pages={self.page_range}")
        elif self.page_numbers:
            parts.append(f"pages={','.join(str(p) for p in self.page_numbers)}")

        if self.sheet_name:
            parts.append(f"sheet={self.sheet_name}")

        return ", ".join(parts)

    def reference_text(self) -> str:
        parts = [self.title_text()]
        if self.location_text():
            parts.append(self.location_text())
        if self.source_url:
            parts.append(self.source_url)
        return " | ".join(parts)

    def to_context_text(self, max_chars: int | None = None) -> str:
        sections: list[str] = []

        title = self.title_text()
        if title:
            sections.append(f"Title: {title}")

        path_text = self.path_text()
        if path_text:
            sections.append(f"Path: {path_text}")

        if self.chunk_kind:
            sections.append(f"Chunk kind: {self.chunk_kind}")

        if self.doc_type:
            sections.append(f"Doc type: {self.doc_type}")

        if self.source_system:
            sections.append(f"Source: {self.source_system}")

        if self.location_text():
            sections.append(f"Location: {self.location_text()}")

        content = self.best_content()
        if content:
            if max_chars is not None and len(content) > max_chars:
                content = content[: max_chars - 3].rstrip() + "..."
            sections.append(f"Content:\n{content}")

        return "\n\n".join(sections)


# ---------------------------------------------------------------------
# Retrieved hit
# ---------------------------------------------------------------------


class RetrievedChunk(BaseModel):
    """
    One retrieval hit returned from Qdrant.
    """

    model_config = ConfigDict(extra="ignore")

    point_id: str | int | None = None
    score: float | None = None
    rank: int | None = None
    payload: ChunkPayload

    @classmethod
    def from_qdrant_point(cls, point: Any, rank: int | None = None) -> "RetrievedChunk":
        raw_payload = getattr(point, "payload", None) or {}
        return cls(
            point_id=getattr(point, "id", None),
            score=getattr(point, "score", None),
            rank=rank,
            payload=ChunkPayload.model_validate(raw_payload),
        )

    def to_agno_reference(self) -> dict[str, Any]:
        return {
            "id": self.payload.chunk_id or (str(self.point_id) if self.point_id is not None else None),
            "title": self.payload.title_text(),
            "content": self.payload.best_content(),
            "metadata": {
                "doc_id": self.payload.doc_id,
                "chunk_id": self.payload.chunk_id,
                "chunk_kind": self.payload.chunk_kind,
                "doc_type": self.payload.doc_type,
                "source_system": self.payload.source_system,
                "source_url": self.payload.source_url,
                "location": self.payload.location_text() or None,
                "section_path": self.payload.section_path or None,
                "heading_path": self.payload.heading_path or None,
                "source_updated_at": self.payload.source_updated_at.isoformat()
                if self.payload.source_updated_at
                else None,
                "quality_score": self.payload.quality_score,
            },
            "score": self.score,
        }

class RetrievalResponse(BaseModel):
    """
    Final response from the retriever before passing results to the agent.
    """

    model_config = ConfigDict(extra="ignore")

    query: str
    hits: list[RetrievedChunk] = Field(default_factory=list)

    @classmethod
    def from_qdrant_points(cls, query: str, points: Iterable[Any]) -> "RetrievalResponse":
        hits = [RetrievedChunk.from_qdrant_point(point, rank=i + 1) for i, point in enumerate(points)]
        return cls(query=query, hits=hits)

    def to_agno_references(self) -> list[dict[str, Any]]:
        return [hit.to_agno_reference() for hit in self.hits]



class PayloadFilterBuilder:
    """
    Converts AccessContext + PayloadFilters into a Qdrant Filter.
    """

    FILTERABLE_LIST_FIELDS = {
        "source_system",
        "doc_type",
        "domains",
        "project_key",
        "space_key",
        "ticket_status",
        "ticket_type",
        "source_type",
        "content_type",
        "chunk_kind",
        "language",
        "doc_id",
        "section_id",
        "external_id",
        "parent_content_id",
        "attachment_id",
        "comment_id",
        "sheet_name",
    }

    @classmethod
    def build(cls, request: RetrievalRequest) -> qmodels.Filter:
        must_conditions: list[Any] = []

        # Mandatory security / lifecycle filters
        must_conditions.append(
            qmodels.FieldCondition(
                key="tenant_id",
                match=qmodels.MatchValue(value=request.access.tenant_id),
            )
        )
        must_conditions.append(
            qmodels.FieldCondition(
                key="is_deleted",
                match=qmodels.MatchValue(value=False),
            )
        )

        # ACL
        if not request.access.is_admin:
            acl_should: list[Any] = [
                qmodels.FieldCondition(
                    key="is_public",
                    match=qmodels.MatchValue(value=True),
                )
            ]

            if request.access.reader_ids:
                acl_should.append(
                    qmodels.FieldCondition(
                        key="acl_readers",
                        match=qmodels.MatchAny(any=request.access.reader_ids),
                    )
                )

            if request.access.space_keys:
                acl_should.append(
                    qmodels.FieldCondition(
                        key="acl_spaces",
                        match=qmodels.MatchAny(any=request.access.space_keys),
                    )
                )

            must_conditions.append(qmodels.Filter(should=acl_should))

        # Business filters
        must_conditions.extend(cls._business_conditions(request.filters))

        return qmodels.Filter(must=must_conditions)

    @classmethod
    def _business_conditions(cls, filters: PayloadFilters) -> list[Any]:
        conditions: list[Any] = []
        data = filters.model_dump(exclude_none=True)

        for field_name, value in data.items():
            if field_name == "min_quality_score":
                conditions.append(
                    qmodels.FieldCondition(
                        key="quality_score",
                        range=qmodels.Range(gte=float(value)),
                    )
                )
                continue

            if field_name == "is_public":
                conditions.append(
                    qmodels.FieldCondition(
                        key="is_public",
                        match=qmodels.MatchValue(value=bool(value)),
                    )
                )
                continue

            if field_name not in cls.FILTERABLE_LIST_FIELDS:
                continue

            if not value:
                continue

            if len(value) == 1:
                conditions.append(
                    qmodels.FieldCondition(
                        key=field_name,
                        match=qmodels.MatchValue(value=value[0]),
                    )
                )
            else:
                conditions.append(
                    qmodels.FieldCondition(
                        key=field_name,
                        match=qmodels.MatchAny(any=value),
                    )
                )

        return conditions