"""ChunkDocument — the retrieval-ready unit stored as one Qdrant point.

One CanonicalDocument produces N ChunkDocuments. This is the contract
between the chunking stage and the Qdrant ingest stage.

Design decisions:
1. chunk_id is deterministic: SHA-256(doc_id + section_id + chunk_position)
   so re-chunking the same content always yields the same ID → idempotent upserts.
2. chunk_text is the raw, dense content to embed (NOT the LLM-enriched summary).
   display_text is the human-readable version shown in the UI citation card.
3. heading_path mirrors SectionNode.path for heading-aware filtered retrieval.
4. ACL fields (acl_readers, acl_spaces, is_public) are mandatory, not optional.
   Every chunk must have an explicit access decision.
5. table_headers / table_row_count are only set for ChunkKind.TABLE_SUMMARY chunks.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ChunkKind(str, Enum):
    """Semantic role of this chunk in its source document."""

    # Text/narrative kinds
    INTRO = "intro"  # Document opening / page intro (no heading)
    SECTION = "section"  # Heading + body text within a section
    COMMENT = "comment"  # User comment (Confluence or Jira)
    RESOLUTION = "resolution"  # Jira resolution / outcome chunk

    # Structured-data kinds
    TABLE_SUMMARY = "table_summary"  # Schema + row-group summary of a table
    TABLE_SCHEMA = "table_schema"  # Column headers + types only
    TABLE_ROW_GROUP = "table_row_group"  # Subset of rows with group summary

    # Document-level kinds
    DOC_HEADER = "doc_header"  # Jira issue header: title+desc+status+priority
    SCHEMA_SUMMARY = "schema_summary"  # Excel/CSV sheet-level overview

    # Attachment / media kinds
    ATTACHMENT = "attachment"  # Binary attachment chunk (PDF page, DOCX section, etc.)
    IMAGE_CAPTION = "image_caption"  # VLM/OCR-generated image description

    # Structured extraction kinds
    KEY_VALUE = "key_value"  # Key-value pairs from forms, headers, etc.
    CHART_SUMMARY = "chart_summary"  # Chart/graph description with data points
    DIAGRAM_SUMMARY = "diagram_summary"  # Diagram description with components/relationships

    # Blog-specific (same logic as page but distinct for filtering)
    BLOG_INTRO = "blog_intro"  # Blog post opening
    BLOG_SECTION = "blog_section"  # Blog post section

    # Database / custom content
    DATABASE_ROW = "database_row"  # Confluence database row


class ChunkDocument(BaseModel):
    """One retrieval-ready chunk to be stored as a single Qdrant point.

    Produced by chunkers; consumed by the embedding + ingest stages.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    tenant_id: str = Field(
        ...,
        description="Tenant/org identifier for mandatory ACL pre-filter. "
        "Default: 'default' for single-tenant deployments.",
    )
    doc_id: str = Field(..., description="Parent CanonicalDocument.document_id")
    chunk_id: str = Field(
        "",
        description="Deterministic SHA-256(doc_id + section_id + chunk_position). "
        "Auto-computed if left empty.",
    )
    section_id: str = Field(
        "",
        description="Deterministic SHA-256(heading_path). "
        "Groups all chunks from the same section.",
    )
    external_id: str = Field(
        "",
        description="Native ID in the source system "
        "(Confluence page_id, Jira issue key, S3 object key).",
    )
    source_url: str = Field("", description="Direct URL to the source page/issue/file.")

    # ── Content ───────────────────────────────────────────────────────────
    doc_title: str = Field(..., description="Title of the parent document.")
    heading: str = Field(
        "",
        description="Immediate section heading this chunk belongs to. "
        "Empty for INTRO chunks.",
    )
    heading_path: list[str] = Field(
        default_factory=list,
        description="Full ancestor path from root to this section. "
        "e.g. ['Chapter 1', 'Section 1.2', 'Subsection 1.2.3']",
    )
    chunk_kind: ChunkKind = ChunkKind.SECTION
    display_text: str = Field(
        ...,
        description="Human-readable text shown in UI citation cards. "
        "May include markdown formatting.",
    )
    chunk_text: str = Field(
        ...,
        description="Plain text used for embedding (no markdown noise). "
        "Heading prepended: '[heading] \\n\\n [body]'",
    )

    # ── LLM Enrichment ────────────────────────────────────────────────────
    summary: str = Field(
        "",
        description="LLM-generated summary of this chunk (from parent doc's "
        "structured_content if available, else empty).",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Key terms for BM25 boosting and filtered retrieval.",
    )
    language: str = Field("", description="ISO 639-1: vi, en, mixed")
    doc_type: str = Field(
        "",
        description="Document type from LLM normalizer: policy, procedure, "
        "data_dictionary, report_spec, etc.",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domain tags: risk, compliance, product, data_engineering, etc.",
    )

    # ── Source-specific metadata ──────────────────────────────────────────
    source_system: str = Field(
        ..., description="confluence, jira, local"
    )
    source_type: str = Field(
        "",
        description="Content type in the source system: page, blogpost, comment, "
        "attachment, issue, worklog, database_row, custom_content. "
        "Maps to SourceContentType enum.",
    )
    content_type: str = Field(
        "",
        description="Fine-grained content type of chunk material: paragraph, "
        "table, code, image, list, heading, mixed. "
        "Maps to ChunkContentType enum.",
    )
    project_key: str = Field("", description="Jira project key (e.g. 'DATA', 'FINX').")
    space_key: str = Field("", description="Confluence space key.")
    ticket_status: str = Field(
        "",
        description="Jira issue status: Open, In Progress, Done, Closed.",
    )
    ticket_type: str = Field(
        "",
        description="Jira issue type: Bug, Task, Story, Epic, Sub-task.",
    )

    # ── Content-graph linking ─────────────────────────────────────────────
    attachment_id: str = Field(
        "",
        description="Confluence/Jira attachment ID. Set for ATTACHMENT chunks.",
    )
    comment_id: str = Field(
        "",
        description="Confluence/Jira comment ID. Set for COMMENT chunks.",
    )
    parent_content_id: str = Field(
        "",
        description="ID of the parent content object (page/issue) this chunk "
        "belongs to. Links attachment/comment chunks to their parent.",
    )
    mime_type: str = Field(
        "",
        description="MIME type of the source content (for attachment chunks). "
        "e.g. application/pdf, image/png.",
    )
    artifact_uri: str = Field(
        "",
        description="URI to the raw artifact (downloaded binary) in the artifact store. "
        "Set for attachment chunks.",
    )
    body_representation: str = Field(
        "",
        description="Confluence body representation used: storage, "
        "atlas_doc_format, export_view.",
    )
    section_path: list[str] = Field(
        default_factory=list,
        description="Structural path for embedding prefix. "
        "e.g. ['Space: ENG', 'Page: API Rate Limits', 'Section: Retry Policy']",
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ── Hashing (change-detection) ────────────────────────────────────────
    doc_hash: str = Field(
        "",
        description="SHA-256 of the raw adapter content (RawDocument.content_hash). "
        "Changes when the source document changes at all.",
    )
    section_hash: str = Field(
        "",
        description="SHA-256 of section title + concatenated block content. "
        "Changes when this specific section changes.",
    )
    chunk_hash: str = Field(
        "",
        description="SHA-256 of chunk_text. "
        "The finest-grained change-detection signal.",
    )

    # ── Embedding metadata ────────────────────────────────────────────────
    embedding_model: str = Field(
        "text-embedding-3-small",
        description="Dense embedding model used for this chunk.",
    )
    embedding_version: str = Field(
        "v2",
        description="Schema version for embedding strategy. "
        "v1: doc_title + heading_path + chunk_text only. "
        "v2: adds display_text, summary, keywords, table metadata, "
        "acronym_expansions for richer semantic embedding.",
    )

    # ── ACL ───────────────────────────────────────────────────────────────
    acl_readers: list[str] = Field(
        default_factory=list,
        description="User/group IDs with read access. "
        "Empty means no individual restriction (use is_public or acl_spaces).",
    )
    acl_spaces: list[str] = Field(
        default_factory=list,
        description="Confluence space keys or Jira project keys that grant access. "
        "Users belonging to these spaces can read this chunk.",
    )
    is_public: bool = Field(
        False,
        description="If True, any authenticated user in this tenant can read this chunk. "
        "Overrides acl_readers and acl_spaces.",
    )

    # ── Soft delete ───────────────────────────────────────────────────────
    is_deleted: bool = Field(
        False,
        description="Soft-delete flag. Set to True when chunk is removed from source "
        "but not yet hard-deleted from Qdrant.",
    )

    # ── Quality ───────────────────────────────────────────────────────────
    quality_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Quality score from LLM normalizer (0.0–1.0).",
    )
    chunk_position: int = Field(
        0,
        ge=0,
        description="Zero-based position of this chunk within its parent document.",
    )
    total_chunks: int = Field(
        0,
        ge=0,
        description="Total number of chunks in the parent document.",
    )

    # ── Table-specific ────────────────────────────────────────────────────
    table_headers: list[str] = Field(
        default_factory=list,
        description="Column headers for TABLE_SUMMARY and TABLE_SCHEMA chunks.",
    )
    table_row_count: int = Field(
        0,
        description="Total rows in the source table (for TABLE_SUMMARY chunks).",
    )

    # ── Attachment / binary-specific ──────────────────────────────────────
    page_range: str = Field(
        "",
        description="PDF page range this chunk covers (e.g. '1-3'). "
        "For attachment chunks parsed from multi-page documents.",
    )
    sheet_name: str = Field(
        "",
        description="Excel/CSV sheet name for spreadsheet attachment chunks.",
    )

    # ── Enhanced fields ─────────────────────────────────────────────────
    page_numbers: list[int] = Field(
        default_factory=list,
        description="PDF page numbers this chunk spans (1-based). For citation support.",
    )
    parent_chunk_id: str = Field(
        "",
        description="chunk_id of the parent chunk for tree traversal. "
        "Empty for top-level chunks (INTRO, DOC_HEADER).",
    )
    pipeline_version: str = Field(
        "",
        description="Pipeline version that produced this chunk. For reprocessing decisions.",
    )
    raw_text: str = Field(
        "",
        description="Original unmodified text from the source, before any cleaning. "
        "Preserved for source fidelity and debugging.",
    )
    embedding_text: str = Field(
        "",
        description="Computed text sent to the embedding model. "
        "Built from structural prefix + display_text + summary + keywords.",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Named entities extracted from this chunk (people, orgs, terms).",
    )

    # ── Domain / terminology ──────────────────────────────────────────────
    acronym_expansions: dict[str, str] = Field(
        default_factory=dict,
        description="Acronym → full-form mappings found in this chunk's context. "
        "e.g. {'CAR': 'Capital Adequacy Ratio', 'NPL': 'Non-Performing Loan'}. "
        "Injected into dense embedding text to help disambiguate domain terms.",
    )

    # ── Computed IDs ──────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _compute_ids(self) -> "ChunkDocument":
        """Auto-compute section_id, chunk_id, chunk_hash if not set."""
        if not self.section_id and self.heading_path:
            raw = "::".join(self.heading_path)
            self.section_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

        if not self.chunk_id:
            raw = f"{self.doc_id}::{self.section_id}::{self.chunk_position}"
            self.chunk_id = hashlib.sha256(raw.encode()).hexdigest()

        if not self.chunk_hash and self.chunk_text:
            self.chunk_hash = hashlib.sha256(self.chunk_text.encode()).hexdigest()

        return self

    model_config = {"use_attribute_docstrings": True}
