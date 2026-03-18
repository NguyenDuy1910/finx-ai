"""Map knowledge document dicts to Qdrant point IDs and payload dicts."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any


def doc_to_point_id(document_id: str) -> str:
    """Convert a hex document_id to a UUID string for use as a Qdrant point ID.

    Uses the first 32 hex characters of the SHA-256 document_id, formatted
    as a UUID.  This is deterministic and stable across pipeline reruns.

    Example:
        "c0c19c9b088edbbb0c195599a49f08a6..." → "c0c19c9b-088e-dbbb-0c19-5599a49f08a6"
    """
    hex32 = document_id[:32].ljust(32, "0")
    return str(uuid.UUID(hex32))


def doc_to_embedding_text(doc: dict) -> str:
    """Build a compact, semantically dense text for embedding.

    Why NOT embed the raw `text` field directly:
    - It contains full Markdown tables, raw URLs, row separators — noisy tokens
    - It often exceeds 8192 tokens, requiring truncation that cuts real content
    - The LLM normalizer already extracted the semantic essence into structured fields

    Strategy: compose from highest-signal enriched fields in priority order:
      title > summary > key_concepts > salient points > entities > definitions > insights
    This produces ~400–1500 clean tokens with dense semantic coverage.
    """
    parts: list[str] = []

    title = doc.get("title", "").strip()
    if title:
        parts.append(f"# {title}")

    doc_type = doc.get("document_type", "")
    domains = doc.get("domains", [])
    if doc_type or domains:
        meta = " | ".join(filter(None, [doc_type] + domains))
        parts.append(f"[{meta}]")

    summary = doc.get("summary", "").strip()
    if summary:
        parts.append(summary)

    structured: dict = doc.get("structured_content", {}) or {}

    # Key concepts
    concepts: list[str] = structured.get("key_concepts", [])
    if concepts:
        parts.append("Concepts: " + ", ".join(str(c) for c in concepts[:20]))

    # Definitions — most precise signal for domain-specific terms
    definitions: list[dict] = structured.get("definitions", [])
    if definitions:
        defs = [f"{d.get('term', '')}: {d.get('meaning', '')}" for d in definitions[:15] if d.get("term")]
        if defs:
            parts.append("Definitions:\n" + "\n".join(defs))

    # Salient points — pre-ranked by priority, high information density
    salient: list[dict] = structured.get("salient_points", [])
    if salient:
        points = []
        for sp in salient[:10]:
            stmt = sp.get("statement", "").strip()
            why = sp.get("why_it_matters", "").strip()
            if stmt:
                points.append(f"- {stmt}" + (f" ({why})" if why else ""))
        if points:
            parts.append("Key points:\n" + "\n".join(points))

    # Insights
    insights: list[dict] = structured.get("insights", [])
    if insights:
        ins = [str(i.get("insight", "")).strip() for i in insights[:5] if i.get("insight")]
        if ins:
            parts.append("Insights:\n" + "\n".join(f"- {i}" for i in ins))

    # Key entities — boosts entity-based retrieval
    entities: list[str] = doc.get("key_entities", [])
    if entities:
        parts.append("Entities: " + ", ".join(str(e) for e in entities[:30]))

    # Abbreviations — critical for Vietnamese/financial domain
    abbrevs: dict = doc.get("abbreviations", {})
    if abbrevs:
        abbrev_parts = [f"{k}={v}" for k, v in list(abbrevs.items())[:20]]
        parts.append("Abbreviations: " + ", ".join(abbrev_parts))

    return "\n\n".join(parts)


# Keep backward-compatible alias used by pipeline.py for content_hash computation
def doc_to_text(doc: dict) -> str:
    """Return the semantic embedding text for a document (uses enriched fields)."""
    return doc_to_embedding_text(doc)


def content_hash(text: str) -> str:
    """SHA-256 fingerprint of the text to embed.  Used for skip-on-rerun."""
    return hashlib.sha256(text.encode()).hexdigest()


def doc_to_payload(doc: dict, ingestion_ts: str | None = None) -> dict[str, Any]:
    """Build the Qdrant payload dict from a knowledge document.

    Only scalar and list-of-scalar fields are included — large nested objects
    (structured_content, tables) are intentionally excluded to keep the payload
    lean and filterable.  They remain available in the source JSON files on disk
    addressable by source_document_id / source_uri.

    Fields added:
    - content_hash: SHA-256 of the embedding text; enables skip-on-rerun
    - ingestion_timestamp: ISO datetime of this ingestion run
    - embedding_strategy: label indicating what content was embedded
    """
    text = doc_to_embedding_text(doc)

    payload: dict[str, Any] = {
        # Identity
        "document_id": doc.get("document_id", ""),
        "source_system": doc.get("source_system", ""),
        "source_uri": doc.get("source_uri", ""),
        "source_document_id": doc.get("source_document_id", ""),
        "source_path": doc.get("_source_path", ""),
        # Display / search
        "title": doc.get("title", ""),
        "summary": doc.get("summary", ""),
        "key_entities": doc.get("key_entities", []),
        # Classification (filterable)
        "document_type": doc.get("document_type", "general"),
        "domains": doc.get("domains", []),
        "language": doc.get("language", ""),
        "space_key": doc.get("space_key", ""),
        # Quality (filterable)
        "quality_score": float(doc.get("quality_score") or 0.0),
        # Timestamps (filterable)
        "processed_at": doc.get("processed_at", ""),
        "ingestion_timestamp": ingestion_ts or datetime.now(timezone.utc).isoformat(),
        # Change-detection
        "content_hash": content_hash(text),
        # Traceability — which embedding strategy produced this point
        "embedding_strategy": "structured_enriched_v1",
    }

    return payload
