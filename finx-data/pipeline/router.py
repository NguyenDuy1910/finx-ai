"""Input Router — classifies raw documents and routes to the correct extractor.

This is Stage 4 of the 7-stage enterprise pipeline. It sits between the
Raw Artifact Store and the parsing / extraction layer.

The router inspects each ``RawDocument``'s mime type, file extension,
source system, and content heuristics to determine which extractor should
handle it.  This replaces the implicit ``can_handle()`` chain with an
explicit, deterministic routing table.

Content Categories
------------------
- **pdf**        → MinerU extractor (or fallback text)
- **html**       → HTML extractor (Confluence pages, HTML exports)
- **markdown**   → Markdown extractor
- **schema**     → Schema extractor (Athena/Glue metadata)
- **csv**        → Markdown extractor (CSV/TSV as text)
- **json**       → Markdown extractor (JSON as text)
- **plaintext**  → Markdown extractor (catch-all text)
- **image**      → MinerU extractor (OCR pathway)
- **binary**     → Unsupported (skipped)
"""

from __future__ import annotations

import logging
import mimetypes
from enum import Enum

from pipeline.adapters.base import RawDocument
from pipeline.extractors.base import BaseExtractor

log = logging.getLogger("finx-data.router")


class ContentCategory(str, Enum):
    """Classification of raw document content."""

    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"
    SCHEMA = "schema"
    CSV = "csv"
    JSON = "json"
    PLAINTEXT = "plaintext"
    IMAGE = "image"
    BINARY = "binary"


# Mapping from mime type prefixes / exact matches → category
_MIME_MAP: dict[str, ContentCategory] = {
    "application/pdf": ContentCategory.PDF,
    "text/html": ContentCategory.HTML,
    "text/markdown": ContentCategory.MARKDOWN,
    "text/csv": ContentCategory.CSV,
    "text/tab-separated-values": ContentCategory.CSV,
    "application/json": ContentCategory.JSON,
    "text/plain": ContentCategory.PLAINTEXT,
    "image/png": ContentCategory.IMAGE,
    "image/jpeg": ContentCategory.IMAGE,
    "image/tiff": ContentCategory.IMAGE,
    "image/webp": ContentCategory.IMAGE,
}

# File extension fallback
_EXT_MAP: dict[str, ContentCategory] = {
    ".pdf": ContentCategory.PDF,
    ".html": ContentCategory.HTML,
    ".htm": ContentCategory.HTML,
    ".md": ContentCategory.MARKDOWN,
    ".markdown": ContentCategory.MARKDOWN,
    ".csv": ContentCategory.CSV,
    ".tsv": ContentCategory.CSV,
    ".json": ContentCategory.JSON,
    ".jsonl": ContentCategory.JSON,
    ".txt": ContentCategory.PLAINTEXT,
    ".png": ContentCategory.IMAGE,
    ".jpg": ContentCategory.IMAGE,
    ".jpeg": ContentCategory.IMAGE,
    ".tiff": ContentCategory.IMAGE,
    ".tif": ContentCategory.IMAGE,
}

# Source systems that always produce a known category
_SOURCE_MAP: dict[str, ContentCategory] = {
    "athena": ContentCategory.SCHEMA,
    "glue": ContentCategory.SCHEMA,
    "confluence": ContentCategory.HTML,
}


def classify(raw: RawDocument) -> ContentCategory:
    """Classify a RawDocument into a ContentCategory.

    Resolution order:
    1. Source system override (e.g. athena → SCHEMA)
    2. Explicit mime_type match
    3. File extension from source_uri
    4. Content heuristics (HTML tags, markdown markers)
    5. Fallback to PLAINTEXT
    """
    # 1. Source system
    system = raw.source_system.lower()
    if system in _SOURCE_MAP:
        return _SOURCE_MAP[system]

    # 2. Mime type
    mime = raw.mime_type.lower().strip() if raw.mime_type else ""
    if mime in _MIME_MAP:
        return _MIME_MAP[mime]
    if mime.startswith("image/"):
        return ContentCategory.IMAGE

    # 3. File extension
    uri = raw.source_uri or ""
    # Strip query params
    clean_uri = uri.split("?")[0].split("#")[0]
    ext = ""
    if "." in clean_uri:
        ext = "." + clean_uri.rsplit(".", 1)[-1].lower()
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]

    # 4. Content heuristics
    if raw.raw_html:
        return ContentCategory.HTML
    content_head = (raw.raw_content or "")[:500]
    if content_head.lstrip().startswith(("<html", "<!DOCTYPE", "<div", "<table")):
        return ContentCategory.HTML
    if raw.binary_content and raw.binary_content[:4] == b"%PDF":
        return ContentCategory.PDF

    # 5. Fallback
    return ContentCategory.PLAINTEXT


class InputRouter:
    """Route RawDocuments to the appropriate extractor based on content classification.

    The router maintains a mapping from ``ContentCategory`` → ``BaseExtractor``
    and provides a deterministic, inspectable routing decision for each document.
    """

    def __init__(self, routing_table: dict[ContentCategory, BaseExtractor]):
        self._table = routing_table

    def route(self, raw: RawDocument) -> tuple[ContentCategory, BaseExtractor | None]:
        """Classify and look up the extractor for a document.

        Returns
        -------
        (category, extractor) — extractor is None if no handler is registered.
        """
        category = classify(raw)
        extractor = self._table.get(category)
        if extractor is None:
            log.warning(
                "No extractor registered for category=%s (uri=%s, mime=%s)",
                category.value,
                raw.source_uri,
                raw.mime_type,
            )
        return category, extractor

    @property
    def categories(self) -> list[ContentCategory]:
        """List of categories that have registered extractors."""
        return list(self._table.keys())
