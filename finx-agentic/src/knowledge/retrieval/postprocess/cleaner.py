"""Step 2 — remove junk from raw retrieval hits.

Drops:
  • image hits without OCR/caption text
  • comment chunks (chunk_kind == "comment")
  • chunks with too little text
  • duplicate section titles (keep first per section)
  • null/zero-score hits unless explicitly requested
"""

from __future__ import annotations

import logging
from typing import List

from src.core.models.retrieval import RetrievedDocument

log = logging.getLogger(__name__)

_MIN_CONTENT_CHARS = 40

_IMAGE_CHUNK_KINDS = frozenset({"image", "figure", "screenshot", "diagram"})
_IMAGE_MIME_PREFIXES = ("image/",)


def clean(
    docs: List[RetrievedDocument],
    *,
    min_content_chars: int = _MIN_CONTENT_CHARS,
    keep_zero_score: bool = False,
) -> List[RetrievedDocument]:
    """Remove junk hits. Returns a new list in the same order."""
    before = len(docs)
    result: list[RetrievedDocument] = []
    seen_section_titles: set[str] = set()

    for doc in docs:
        meta = doc.meta_data

        # 1. Drop image chunks that have no usable text
        if _is_empty_image(doc):
            continue

        # 2. Drop comment chunks
        if (meta.get("chunk_kind") or "").lower() == "comment":
            continue

        # 3. Drop chunks with too little text
        text = (doc.content or "").strip()
        if len(text) < min_content_chars:
            continue

        # 4. Drop null / zero-score hits (unless explicitly kept)
        if not keep_zero_score:
            score = meta.get("qdrant_score") or meta.get("boosted_score") or 0.0
            if score == 0.0:
                continue

        # 5. Deduplicate section titles — keep first occurrence per section
        section_key = _section_dedup_key(doc)
        if section_key:
            if section_key in seen_section_titles:
                continue
            seen_section_titles.add(section_key)

        result.append(doc)

    dropped = before - len(result)
    if dropped:
        log.debug("Cleaner: dropped %d / %d junk hits", dropped, before)
    return result


def _is_empty_image(doc: RetrievedDocument) -> bool:
    """True if the hit is an image chunk lacking OCR/caption content."""
    meta = doc.meta_data
    chunk_kind = (meta.get("chunk_kind") or "").lower()
    mime = (meta.get("mime_type") or "").lower()
    content_type = (meta.get("content_type") or "").lower()

    is_image = (
        chunk_kind in _IMAGE_CHUNK_KINDS
        or any(mime.startswith(p) for p in _IMAGE_MIME_PREFIXES)
        or content_type == "image"
    )
    if not is_image:
        return False

    # Has meaningful text (OCR result or caption)? Keep it.
    text = (doc.content or "").strip()
    return len(text) < _MIN_CONTENT_CHARS


def _section_dedup_key(doc: RetrievedDocument) -> str | None:
    """Return a dedup key if the chunk is a section title / header only.

    We deduplicate these because multiple heading-only chunks from the same
    section are noise.  Regular content chunks are never deduped here.
    """
    meta = doc.meta_data
    chunk_kind = (meta.get("chunk_kind") or "").lower()

    # Only deduplicate heading/section-title chunks
    if chunk_kind not in ("section_title", "heading", "doc_header"):
        return None

    doc_id = meta.get("doc_id", "")
    section_id = meta.get("section_id", "")
    heading = meta.get("heading", "")

    if doc_id and section_id:
        return f"{doc_id}::{section_id}"
    if doc_id and heading:
        return f"{doc_id}::{heading}"
    return None
