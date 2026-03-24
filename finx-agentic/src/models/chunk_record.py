from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Any

from src.models._helpers import (
    clean_dict,
    clean_list,
    parse_datetime,
    sha256_text,
    utcnow,
)


class ChunkKind(str, Enum):
    # ── Text / narrative ──────────────────────────────────────────────────
    SECTION = "section"
    INTRO = "intro"
    COMMENT = "comment"
    RESOLUTION = "resolution"
    CODE = "code"
    LIST = "list"
    MIXED = "mixed"

    # ── Structured data ───────────────────────────────────────────────────
    TABLE_SUMMARY = "table_summary"
    TABLE_SCHEMA = "table_schema"
    TABLE_ROW_GROUP = "table_row_group"
    SCHEMA_SUMMARY = "schema_summary"
    KEY_VALUE = "key_value"

    # ── Document-level ────────────────────────────────────────────────────
    DOC_HEADER = "doc_header"

    # ── Attachment / media ────────────────────────────────────────────────
    ATTACHMENT = "attachment"
    IMAGE = "image"
    IMAGE_CAPTION = "image_caption"
    CHART_SUMMARY = "chart_summary"
    DIAGRAM_SUMMARY = "diagram_summary"

    # ── Blog-specific ─────────────────────────────────────────────────────
    BLOG_INTRO = "blog_intro"
    BLOG_SECTION = "blog_section"

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_ROW = "database_row"


@dataclass(slots=True)
class ChunkRecord:
    # ── Identity ──────────────────────────────────────────────────────────
    tenant_id: str
    doc_id: str
    chunk_id: str | None = None
    section_id: str | None = None
    external_id: str | None = None
    source_url: str | None = None

    # ── Content ───────────────────────────────────────────────────────────
    source_system: str = "unknown"
    doc_title: str = ""
    heading: str = ""
    heading_path: list[str] = field(default_factory=list)
    chunk_kind: ChunkKind | str = ChunkKind.SECTION
    display_text: str = ""
    chunk_text: str = ""

    # ── LLM Enrichment ────────────────────────────────────────────────────
    summary: str | None = None
    keywords: list[str] = field(default_factory=list)
    language: str | None = None
    doc_type: str | None = None
    domains: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    acronym_expansions: dict[str, str] = field(default_factory=dict)

    # ── Source Metadata ───────────────────────────────────────────────────
    source_type: str | None = None
    content_type: str = "paragraph"
    project_key: str | None = None
    space_key: str | None = None
    ticket_status: str | None = None
    ticket_type: str | None = None

    # ── Content-Graph Linking ─────────────────────────────────────────────
    attachment_id: str | None = None
    comment_id: str | None = None
    parent_content_id: str | None = None
    mime_type: str | None = None
    artifact_uri: str | None = None
    body_representation: str | None = None
    section_path: list[str] = field(default_factory=list)

    # ── Timestamps & Hashing ──────────────────────────────────────────────
    source_created_at: datetime | str | None = None
    source_updated_at: datetime | str | None = None
    ingested_at: datetime | str = field(default_factory=utcnow)
    doc_hash: str | None = None
    section_hash: str | None = None
    chunk_hash: str | None = None

    # ── Embedding Metadata ────────────────────────────────────────────────
    embedding_model: str = "text-embedding-3-small"
    embedding_version: str = "v2"
    embedding_text: str | None = None
    raw_text: str | None = None

    # ── ACL & Access ──────────────────────────────────────────────────────
    acl_readers: list[str] = field(default_factory=list)
    acl_spaces: list[str] = field(default_factory=list)
    is_public: bool = False
    is_deleted: bool = False

    # ── Quality & Position ────────────────────────────────────────────────
    quality_score: float = 1.0
    chunk_position: int = 0
    total_chunks: int = 1
    pipeline_version: str = "v1"

    # ── Structured / Attachment-Specific ─────────────────────────────────
    table_headers: list[str] = field(default_factory=list)
    table_row_count: int | None = None
    page_range: str | None = None
    page_numbers: list[int] = field(default_factory=list)
    sheet_name: str | None = None
    parent_chunk_id: str | None = None

    def __post_init__(self) -> None:
        self.tenant_id = self.tenant_id.strip()
        self.doc_id = self.doc_id.strip()
        self.doc_title = self.doc_title.strip()
        self.heading = self.heading.strip()
        self.source_system = self.source_system.strip().lower()
        self.content_type = self.content_type.strip().lower()

        self.source_type = self.source_type.strip().lower() if self.source_type else None
        self.doc_type = self.doc_type.strip().lower() if self.doc_type else None
        self.language = self.language.strip().lower() if self.language else None
        self.project_key = self.project_key.strip() if self.project_key else None
        self.space_key = self.space_key.strip() if self.space_key else None
        self.ticket_status = self.ticket_status.strip() if self.ticket_status else None
        self.ticket_type = self.ticket_type.strip() if self.ticket_type else None
        self.mime_type = self.mime_type.strip().lower() if self.mime_type else None
        self.body_representation = self.body_representation.strip() if self.body_representation else None
        self.pipeline_version = self.pipeline_version.strip()
        self.embedding_model = self.embedding_model.strip()
        self.embedding_version = self.embedding_version.strip()

        self.heading_path = clean_list(self.heading_path)
        self.section_path = clean_list(self.section_path) or list(self.heading_path)
        self.keywords = clean_list(self.keywords)
        self.domains = clean_list(self.domains)
        self.entities = clean_list(self.entities)
        self.acl_readers = clean_list(self.acl_readers)
        self.acl_spaces = clean_list(self.acl_spaces)
        self.table_headers = clean_list(self.table_headers)
        self.page_numbers = sorted({int(x) for x in self.page_numbers if int(x) > 0})
        self.acronym_expansions = clean_dict(self.acronym_expansions)

        self.chunk_text = self.chunk_text.strip()
        self.display_text = self.display_text.strip()
        self.summary = self.summary.strip() if self.summary else None
        self.embedding_text = self.embedding_text.strip() if self.embedding_text else None
        self.raw_text = self.raw_text if self.raw_text is None else self.raw_text.strip()

        self.source_created_at = parse_datetime(self.source_created_at)
        self.source_updated_at = parse_datetime(self.source_updated_at)
        self.ingested_at = parse_datetime(self.ingested_at) or utcnow()

        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if not self.doc_id:
            raise ValueError("doc_id is required")
        if self.chunk_position < 0:
            raise ValueError("chunk_position must be >= 0")
        if self.total_chunks <= 0:
            raise ValueError("total_chunks must be > 0")
        if self.chunk_position >= self.total_chunks:
            self.total_chunks = self.chunk_position + 1
        if not (0.0 <= self.quality_score <= 1.0):
            raise ValueError("quality_score must be between 0.0 and 1.0")

        if not isinstance(self.chunk_kind, ChunkKind):
            self.chunk_kind = ChunkKind(str(self.chunk_kind).strip().lower())

        if not self.section_id:
            self.section_id = self.compute_section_id()
        if not self.chunk_id:
            self.chunk_id = self.compute_chunk_id()
        if not self.section_hash:
            self.section_hash = self.compute_section_hash()
        if not self.chunk_hash:
            self.chunk_hash = self.compute_chunk_hash()
        if not self.display_text:
            self.display_text = self.build_display_text()
        if not self.embedding_text:
            self.embedding_text = self.build_embedding_text()

    @property
    def canonical_path(self) -> list[str]:
        if self.section_path:
            return self.section_path
        if self.heading_path:
            return self.heading_path
        if self.heading:
            return [self.heading]
        if self.doc_title:
            return [self.doc_title]
        return []

    @property
    def is_table_like(self) -> bool:
        return self.chunk_kind in {
            ChunkKind.TABLE_SUMMARY,
            ChunkKind.TABLE_SCHEMA,
            ChunkKind.TABLE_ROW_GROUP,
        }

    @property
    def is_attachment(self) -> bool:
        return self.chunk_kind == ChunkKind.ATTACHMENT

    @property
    def is_comment(self) -> bool:
        return self.chunk_kind == ChunkKind.COMMENT

    @property
    def best_title(self) -> str:
        if self.heading:
            return self.heading
        if self.heading_path:
            return self.heading_path[-1]
        return self.doc_title

    def compute_section_id(self) -> str:
        path = " / ".join(self.canonical_path)
        seed = path or self.doc_title or self.doc_id
        return sha256_text(seed)

    def compute_chunk_id(self) -> str:
        seed = f"{self.doc_id}:{self.section_id}:{self.chunk_position}"
        return sha256_text(seed)

    def compute_section_hash(self) -> str:
        heading_text = " / ".join(self.canonical_path)
        seed = f"{heading_text}\n{self.chunk_text}"
        return sha256_text(seed)

    def compute_chunk_hash(self) -> str:
        return sha256_text(self.chunk_text)

    def build_display_text(self, max_chars: int = 320) -> str:
        source = self.summary or self.chunk_text or self.raw_text or self.doc_title
        source = " ".join(source.split())
        if len(source) <= max_chars:
            return source
        return source[: max_chars - 1].rstrip() + "…"

    def build_embedding_text(self) -> str:
        parts: list[str] = []

        if self.doc_title:
            parts.append(f"Title: {self.doc_title}")

        if self.canonical_path:
            parts.append(f"Path: {' > '.join(self.canonical_path)}")

        if self.heading and self.heading != self.doc_title:
            parts.append(f"Heading: {self.heading}")

        if self.doc_type:
            parts.append(f"DocType: {self.doc_type}")

        if self.domains:
            parts.append(f"Domains: {', '.join(self.domains)}")

        if self.summary:
            parts.append(f"Summary: {self.summary}")

        if self.keywords:
            parts.append(f"Keywords: {', '.join(self.keywords)}")

        if self.entities:
            parts.append(f"Entities: {', '.join(self.entities)}")

        if self.acronym_expansions:
            expansions = "; ".join(f"{k} = {v}" for k, v in self.acronym_expansions.items())
            parts.append(f"Acronyms: {expansions}")

        if self.chunk_text:
            parts.append(f"Content:\n{self.chunk_text}")

        return "\n".join(part for part in parts if part).strip()

    def location_hint(self) -> str | None:
        if self.page_range:
            return f"pages {self.page_range}"
        if self.page_numbers:
            return "pages " + ", ".join(str(x) for x in self.page_numbers)
        if self.sheet_name:
            return f"sheet {self.sheet_name}"
        if self.heading_path:
            return " > ".join(self.heading_path)
        if self.heading:
            return self.heading
        return None

    def best_excerpt(self, max_chars: int = 480) -> str:
        text = self.chunk_text or self.display_text or self.summary or ""
        normalized = " ".join(text.split())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 1].rstrip() + "…"

    def refresh_derived_fields(self) -> None:
        self.section_id = self.compute_section_id()
        self.chunk_id = self.compute_chunk_id()
        self.section_hash = self.compute_section_hash()
        self.chunk_hash = self.compute_chunk_hash()
        self.display_text = self.build_display_text()
        self.embedding_text = self.build_embedding_text()

    def clone_with(self, **changes: Any) -> "ChunkRecord":
        clone = replace(self, **changes)
        clone.refresh_derived_fields()
        return clone

    def to_qdrant_payload(
        self,
        *,
        include_text: bool = True,
        include_raw_text: bool = False,
    ) -> dict[str, Any]:
        payload = asdict(self)
        payload["chunk_kind"] = self.chunk_kind.value

        for field_name in ("source_created_at", "source_updated_at", "ingested_at"):
            value = getattr(self, field_name)
            payload[field_name] = value.isoformat() if isinstance(value, datetime) else None

        if not include_text:
            payload.pop("chunk_text", None)
            payload.pop("display_text", None)
            payload.pop("summary", None)
            payload.pop("embedding_text", None)

        if not include_raw_text:
            payload.pop("raw_text", None)

        return payload

    def to_filterable_payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "section_id": self.section_id,
            "source_system": self.source_system,
            "source_type": self.source_type,
            "content_type": self.content_type,
            "chunk_kind": self.chunk_kind.value,
            "doc_type": self.doc_type,
            "domains": self.domains,
            "language": self.language,
            "space_key": self.space_key,
            "project_key": self.project_key,
            "acl_spaces": self.acl_spaces,
            "is_public": self.is_public,
            "is_deleted": self.is_deleted,
            "quality_score": self.quality_score,
            "chunk_position": self.chunk_position,
            "total_chunks": self.total_chunks,
            "source_updated_at": self.source_updated_at.isoformat() if self.source_updated_at else None,
        }

    def to_retrieved_document(self) -> "RetrievedDocument":
        """Convert to RetrievedDocument for the postprocess pipeline."""
        from src.core.models.retrieval import RetrievedDocument

        doc_title = self.doc_title or ""
        heading = self.heading or ""
        title_parts = [p for p in (doc_title, heading) if p]
        name = " > ".join(title_parts) if title_parts else "Untitled chunk"

        content = self.display_text or self.chunk_text or self.summary or ""

        meta: dict[str, Any] = {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "section_id": self.section_id,
            "source_system": self.source_system,
            "source_url": self.source_url,
            "chunk_kind": self.chunk_kind.value if isinstance(self.chunk_kind, ChunkKind) else self.chunk_kind,
            "chunk_position": self.chunk_position,
            "total_chunks": self.total_chunks,
            "quality_score": self.quality_score,
        }

        return RetrievedDocument(
            name=name,
            content=content,
            meta_data={k: v for k, v in meta.items() if v is not None},
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChunkRecord":
        """Construct from a Qdrant payload dict, ignoring unknown keys."""
        import dataclasses

        known_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in payload.items() if k in known_fields}
        return cls(**filtered)