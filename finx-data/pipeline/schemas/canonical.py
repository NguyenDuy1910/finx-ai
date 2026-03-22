from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .blocks import BlockProvenance, ContentBlock, LinkRef, SectionNode
from .provenance import Provenance


class CanonicalDocument(BaseModel):
    """The canonical output format for the preprocessing pipeline.

    This is the contract between finx-data and all downstream consumers
    (bootstrap indexing, knowledge graph, vector store).
    """
    model_config = {"use_attribute_docstrings": True}


    # ── Identity ──────────────────────────────────────────────────────────
    document_id: str = Field(
        "",
        description="Deterministic SHA-256 hash of (source_system, source_uri). "
        "Auto-computed if left empty.",
    )
    source_system: str = Field(
        ..., description="Origin system: confluence, jira, local"
    )
    source_uri: str = Field(
        ..., description="Unique locator within the source system"
    )
    source_document_id: str = Field(
        "",
        description="Native ID in the source system (e.g. Confluence page_id, Glue table name)",
    )

    # ── Content identity ──────────────────────────────────────────────────
    title: str = ""
    content_type: str = Field(
        "document",
        description="High-level type: document, schema, api_spec, faq, etc.",
    )
    source_content_type: str = Field(
        "",
        description="Source-specific content type: page, blogpost, comment, "
        "attachment, issue, worklog, custom_content, database_row, etc. "
        "Maps to SourceContentType enum values.",
    )
    parent_document_id: str = Field(
        "",
        description="document_id of the parent content object. "
        "Links comments/attachments back to their parent page/issue.",
    )
    version: int = Field(
        0,
        description="Content version from the source system for change detection.",
    )

    # ── Structure ─────────────────────────────────────────────────────────
    section_hierarchy: list[SectionNode] = Field(
        default_factory=list,
        description="Tree of document sections preserving heading structure",
    )
    content_blocks: list[ContentBlock] = Field(
        default_factory=list,
        description="Ordered list of typed content blocks",
    )
    block_provenance: list[BlockProvenance] = Field(
        default_factory=list,
        description="Per-block provenance, parallel to content_blocks. "
        "If non-empty, block_provenance[i] corresponds to content_blocks[i].",
    )

    # ── Structured extractions ────────────────────────────────────────────
    links: list[LinkRef] = Field(default_factory=list)

    # ── Metadata ──────────────────────────────────────────────────────────
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-specific metadata (space_key, database, owner, tags, …)",
    )
    tags: list[str] = Field(default_factory=list)

    # ── Provenance ────────────────────────────────────────────────────────
    provenance: Provenance = Field(default_factory=Provenance)

    # ── Timestamps ────────────────────────────────────────────────────────
    source_created_at: datetime | None = None
    source_modified_at: datetime | None = None
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="after")
    def _compute_document_id(self) -> "CanonicalDocument":
        """Deterministically compute document_id from source coordinates."""
        if not self.document_id:
            raw = f"{self.source_system}::{self.source_uri}"
            self.document_id = hashlib.sha256(raw.encode()).hexdigest()
        return self

    # ── Convenience ───────────────────────────────────────────────────────

    def full_text(self) -> str:
        """Concatenate all text-bearing blocks into a single string.

        Useful for quick vector embedding or quality checks.
        """
        parts: list[str] = []
        for block in self.content_blocks:
            if hasattr(block, "content") and block.content:
                parts.append(block.content)
            elif hasattr(block, "markdown") and block.markdown:
                parts.append(block.markdown)
            elif hasattr(block, "items"):
                parts.append("\n".join(block.items))
            elif hasattr(block, "description") and block.description:
                parts.append(block.description)
            elif hasattr(block, "pairs"):
                # KeyValueBlock
                lines = [f"{p.get('key', '')}: {p.get('value', '')}" for p in block.pairs if p.get("key")]
                if lines:
                    parts.append("\n".join(lines))
            elif hasattr(block, "trend_summary") and block.trend_summary:
                # ChartBlock
                parts.append(block.trend_summary)
            elif hasattr(block, "components"):
                # DiagramBlock
                if block.description:
                    parts.append(block.description)
        return "\n\n".join(parts)

    def word_count(self) -> int:
        return len(self.full_text().split())

    def to_embedding_chunks(
        self, max_tokens: int = 512, overlap: int = 64
    ) -> list[dict[str, Any]]:
        """Split into overlapping text chunks suitable for vector embedding.

        Each chunk inherits the document's metadata and section path for
        filtered retrieval.
        """
        full = self.full_text()
        words = full.split()
        chunks: list[dict[str, Any]] = []
        step = max(1, max_tokens - overlap)

        for i in range(0, len(words), step):
            chunk_words = words[i : i + max_tokens]
            if not chunk_words:
                break
            chunks.append(
                {
                    "document_id": self.document_id,
                    "source_system": self.source_system,
                    "source_uri": self.source_uri,
                    "title": self.title,
                    "chunk_index": len(chunks),
                    "text": " ".join(chunk_words),
                    "metadata": self.metadata,
                    "tags": self.tags,
                }
            )
        return chunks

    def to_graph_payload(self) -> dict[str, Any]:
        """Produce a dict suitable for graph extraction bootstrap.

        Compatible with the shape expected by finx-agentic's
        ``scripts/bootstrap/chunk_builder.py``.
        """
        return {
            "document_id": self.document_id,
            "source_system": self.source_system,
            "source_uri": self.source_uri,
            "source_document_id": self.source_document_id,
            "title": self.title,
            "content_type": self.content_type,
            "content": self.full_text(),
            "tables": [
                {
                    "headers": b.headers,
                    "rows": b.rows,
                    "caption": b.caption,
                    "markdown": b.markdown,
                }
                for b in self.content_blocks
                if hasattr(b, "headers")
            ],
            "links": [l.model_dump() for l in self.links],
            "metadata": self.metadata,
            "tags": self.tags,
            "processed_at": self.processed_at.isoformat(),
        }
