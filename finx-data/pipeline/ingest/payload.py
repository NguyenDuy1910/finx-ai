from __future__ import annotations

import uuid
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


_TABLE_KINDS = frozenset({
    ChunkKind.TABLE_SUMMARY, ChunkKind.TABLE_SCHEMA,
    ChunkKind.TABLE_ROW_GROUP, ChunkKind.SCHEMA_SUMMARY,
})

_SUMMARY_MAX_WORDS = 40


def _build_dense_text(chunk: ChunkDocument) -> str:
    """Build text for the dense (semantic) embedding vector.

    Dense embeddings capture *meaning*. We include only high-signal
    fields and keep token count tight to avoid dilution.

    Layers (each separated by ``\\n\\n``):
        1. doc_title + heading   — anchors the semantic space
        2. body content          — display_text preferred (richer), else chunk_text
        3. short summary         — only ≤ 40 words; paraphrases add marginal gain
        4. table column headers  — strong semantic signal for structured data
    """
    sections: list[str] = []

    # 1. Lightweight structural anchor — title + heading only.
    #    Avoids full heading_path / section_path which add noise.
    title = chunk.doc_title
    if chunk.heading:
        sections.append(f"{title} > {chunk.heading}")
    else:
        sections.append(title)

    # 2. Core content — pick the richer representation.
    body = chunk.display_text or chunk.chunk_text
    if body:
        sections.append(body)

    # 3. Summary — only very short ones; longer summaries duplicate the body.
    if chunk.summary and len(chunk.summary.split()) <= _SUMMARY_MAX_WORDS:
        sections.append(chunk.summary)

    # 4. Table headers — column names carry strong topical signal.
    if chunk.chunk_kind in _TABLE_KINDS and chunk.table_headers:
        sections.append(f"Columns: {', '.join(chunk.table_headers)}")

    return "\n\n".join(sections)


def _build_sparse_text(chunk: ChunkDocument) -> str:
    """Build text for the sparse (lexical/BM25) embedding vector.

    Sparse vectors power exact-term matching. We combine every field
    that users might type verbatim: titles, headings, raw content,
    keywords, column names, and acronym expansions (both forms).
    """
    parts: list[str] = []

    # Document & section identifiers — users search by name.
    if chunk.doc_title:
        parts.append(chunk.doc_title)
    if chunk.heading:
        parts.append(chunk.heading)

    # Raw content — the primary term source.
    parts.append(chunk.chunk_text)

    # Keywords — explicit term-boost, ideal for sparse.
    if chunk.keywords:
        parts.append(" ".join(chunk.keywords))

    # Table column headers — users search by column name.
    if chunk.chunk_kind in _TABLE_KINDS and chunk.table_headers:
        parts.append(" ".join(chunk.table_headers))

    # Acronym expansions — both the abbreviation and its full form
    # so searches for "OTP" and "One-Time Password" both hit.
    if chunk.acronym_expansions:
        for abbr, full in chunk.acronym_expansions.items():
            parts.append(f"{abbr} {full}")

    return "\n".join(parts)


def chunk_to_embedding_texts(chunk: ChunkDocument) -> tuple[str, str]:
    """Return ``(dense_text, sparse_text)`` for a chunk.

    - **dense_text** → sent to the embedding model (semantic vector).
    - **sparse_text** → hashed into a sparse vector (lexical matching).
    """
    return _build_dense_text(chunk), _build_sparse_text(chunk)


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
        "chunk_text": chunk.chunk_text,
        "display_text": chunk.display_text or "",

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
        # ── Attachment / Document Location ────────────────────────────────────
        "page_range": chunk.page_range or None,
        "sheet_name": chunk.sheet_name or None,
        "page_numbers": chunk.page_numbers or None,
        # ── Terminology ──────────────────────────────────────────────────
        "acronym_expansions": chunk.acronym_expansions or None,

        # ── Enhanced fields ──────────────────────────────────────────────
        "pipeline_version": chunk.pipeline_version or None,
        "parent_chunk_id": chunk.parent_chunk_id or None,
        "entities": chunk.entities or None,
    }

    # Remove None values to keep payload lean and efficient
    return {k: v for k, v in payload.items() if v is not None}
