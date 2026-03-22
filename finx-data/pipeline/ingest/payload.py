from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from pipeline.schemas.chunk import ChunkDocument, ChunkKind


def chunk_to_point_id(chunk_id: str) -> str:
    """Convert a hex chunk_id to a UUID string for use as a Qdrant point ID.

    Uses the first 32 hex characters of the SHA-256 chunk_id.
    Deterministic and stable across reruns.

    Args:
        chunk_id: 64-char SHA-256 hex string

    Returns:
        UUID string for Qdrant point ID

    Example:
        "c0c19c9b088edbbb0c195599a49f08a6..." → "c0c19c9b-088e-dbbb-0c19-5599a49f08a6"
    """
    hex32 = chunk_id[:32].ljust(32, "0")
    return str(uuid.UUID(hex32))


def _build_heading_prefix(chunk: ChunkDocument) -> str:
    """Build the '[doc_title] path > heading' prefix line."""
    parts = [f"[{chunk.doc_title}]"]
    if chunk.heading_path:
        parts.append(" > ".join(chunk.heading_path))
    if chunk.heading:
        parts.append(chunk.heading)
    return " > ".join(parts) if len(parts) > 1 else parts[0]


def _build_dense_text(chunk: ChunkDocument) -> str:
    """Assemble rich embedding text for dense (semantic) vector.

    Combines structural context + content + LLM enrichments so the
    embedding captures both *what* the chunk says and *where* it sits.

    Layer order (each on its own paragraph):
        1. doc_title  +  heading_path / heading          (structural)
        2. display_text  (main human-readable content)   (content)
        3. summary — only if short and accurate           (semantic boost)
        4. keywords                                       (term boost)
        5. kind-specific metadata:
           - table_summary / table_schema → table headers + schema context
           - spreadsheet / SCHEMA_SUMMARY → column descriptions
           - COMMENT                      → comment_text already in chunk_text
           - RESOLUTION                   → resolution already in chunk_text
        6. acronym_expansions                             (disambiguation)
    """
    sections: list[str] = []

    # ── 1. structural prefix ─────────────────────────────────────────────
    # Prefer section_path (content-graph prefix) if available
    if chunk.section_path:
        sections.append("\n".join(f"[{p}]" for p in chunk.section_path))
    else:
        sections.append(_build_heading_prefix(chunk))

    body = chunk.display_text or chunk.chunk_text
    if body:
        sections.append(body)

    # ── 3. summary (short only — avoids diluting the embedding) ──────────
    if chunk.summary:
        word_count = len(chunk.summary.split())
        # Only include summaries ≤ 60 words — long summaries add noise
        if word_count <= 60:
            sections.append(f"Summary: {chunk.summary}")

    # ── 4. keywords ──────────────────────────────────────────────────────
    if chunk.keywords:
        sections.append(f"Keywords: {', '.join(chunk.keywords)}")

    # ── 5. kind-specific metadata ────────────────────────────────────────
    kind = chunk.chunk_kind

    if kind in (ChunkKind.TABLE_SUMMARY, ChunkKind.TABLE_SCHEMA, ChunkKind.TABLE_ROW_GROUP):
        # table_headers are always useful for matching column-name queries
        if chunk.table_headers:
            sections.append(f"Columns: {', '.join(chunk.table_headers)}")
        if chunk.table_row_count:
            sections.append(f"Total rows: {chunk.table_row_count}")

    if kind == ChunkKind.SCHEMA_SUMMARY:
        # For spreadsheet/schema chunks the chunk_text already contains
        # column descriptions — no extra layer needed, but add headers
        # separately so partial column-name queries still hit.
        if chunk.table_headers:
            sections.append(f"Columns: {', '.join(chunk.table_headers)}")

    # KEY_VALUE chunks: content already in chunk_text — no extra layer.

    # CHART_SUMMARY: content already in chunk_text — include chart type for matching.
    if kind == ChunkKind.CHART_SUMMARY and chunk.content_type == "chart":
        sections.append("Content type: chart/graph")

    # DIAGRAM_SUMMARY: content already in chunk_text — include type for matching.
    if kind == ChunkKind.DIAGRAM_SUMMARY and chunk.content_type == "diagram":
        sections.append("Content type: diagram")

    # COMMENT and RESOLUTION kinds: their chunk_text already carries the
    # "[Comment by …]" / resolution preamble — no extra layer needed.

    # ── 6. acronym expansions ────────────────────────────────────────────
    if chunk.acronym_expansions:
        expansions = "; ".join(
            f"{acr} = {full}" for acr, full in chunk.acronym_expansions.items()
        )
        sections.append(f"Terminology: {expansions}")

    return "\n\n".join(sections)


def chunk_to_embedding_texts(chunk: ChunkDocument) -> tuple[str, str]:

    dense_text = _build_dense_text(chunk)

    # Sparse embedding: raw text only (keyword matching should match actual
    # document terms without structural noise)
    sparse_text = chunk.chunk_text

    return dense_text, sparse_text


def chunk_to_payload(chunk: ChunkDocument) -> dict[str, Any]:

    payload: dict[str, Any] = {
        # ── Identity ──────────────────────────────────────────────────────
        "tenant_id": chunk.tenant_id,
        "doc_id": chunk.doc_id,
        "chunk_id": chunk.chunk_id,
        "section_id": chunk.section_id,
        "external_id": chunk.external_id,
        "source_url": chunk.source_url,

        # ── Content ───────────────────────────────────────────────────────
        "source_system": chunk.source_system,
        "doc_title": chunk.doc_title,
        "heading": chunk.heading,
        "heading_path": chunk.heading_path,
        "chunk_kind": chunk.chunk_kind.value,

        # ── Classification ────────────────────────────────────────────────
        "language": chunk.language,
        "doc_type": chunk.doc_type,
        "domains": chunk.domains,
        "project_key": chunk.project_key,
        "space_key": chunk.space_key,
        "ticket_status": chunk.ticket_status,
        "ticket_type": chunk.ticket_type,
        "source_type": chunk.source_type,
        "content_type": chunk.content_type,

        # ── Content-Graph Linking ─────────────────────────────────────────
        "attachment_id": chunk.attachment_id,
        "comment_id": chunk.comment_id,
        "parent_content_id": chunk.parent_content_id,
        "mime_type": chunk.mime_type,
        "artifact_uri": chunk.artifact_uri,
        "body_representation": chunk.body_representation,
        "section_path": chunk.section_path,

        # ── LLM Enrichment ────────────────────────────────────────────────
        "summary": chunk.summary,
        "keywords": chunk.keywords,

        # ── Timestamps ────────────────────────────────────────────────────
        "source_created_at": chunk.source_created_at.isoformat() if chunk.source_created_at else None,
        "source_updated_at": chunk.source_updated_at.isoformat() if chunk.source_updated_at else None,
        "ingested_at": chunk.ingested_at.isoformat(),

        # ── Change Detection ──────────────────────────────────────────────
        "doc_hash": chunk.doc_hash,
        "section_hash": chunk.section_hash,
        "chunk_hash": chunk.chunk_hash,

        # ── Embedding Metadata ────────────────────────────────────────────
        "embedding_model": chunk.embedding_model,
        "embedding_version": chunk.embedding_version,

        # ── ACL ───────────────────────────────────────────────────────────
        "acl_readers": chunk.acl_readers,
        "acl_spaces": chunk.acl_spaces,
        "is_public": chunk.is_public,

        # ── Soft Delete ───────────────────────────────────────────────────
        "is_deleted": chunk.is_deleted,

        # ── Quality ───────────────────────────────────────────────────────
        "quality_score": chunk.quality_score,
        "chunk_position": chunk.chunk_position,
        "total_chunks": chunk.total_chunks,

        # ── Table-Specific ────────────────────────────────────────────────
        "table_headers": chunk.table_headers,
        "table_row_count": chunk.table_row_count,

        # ── Terminology ──────────────────────────────────────────────────
        "acronym_expansions": chunk.acronym_expansions or None,

        # ── Enhanced fields ──────────────────────────────────────────────
        "pipeline_version": chunk.pipeline_version or None,
        "parent_chunk_id": chunk.parent_chunk_id or None,
        "entities": chunk.entities or None,
    }

    # Remove None values to keep payload lean and efficient
    return {k: v for k, v in payload.items() if v is not None}
