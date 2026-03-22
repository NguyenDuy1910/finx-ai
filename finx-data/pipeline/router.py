"""Input Router -- classifies raw documents and routes to the correct extractor.

Confluence and Jira documents are sub-routed by ``content_type`` (page,
blogpost, comment, attachment) so that each content object gets the
most appropriate extractor.
"""

from __future__ import annotations

import logging
from enum import Enum

from pipeline.adapters.base import RawDocument
from pipeline.extractors.base import BaseExtractor

log = logging.getLogger("finx-data.router")


class ContentCategory(str, Enum):
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"
    SCHEMA = "schema"
    CSV = "csv"
    JSON = "json"
    PLAINTEXT = "plaintext"
    IMAGE = "image"
    BINARY = "binary"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"

    # Confluence-specific sub-categories
    CONFLUENCE_PAGE = "confluence_page"
    CONFLUENCE_COMMENT = "confluence_comment"
    CONFLUENCE_ATTACHMENT = "confluence_attachment"

    # Jira-specific sub-categories
    JIRA_ISSUE = "jira_issue"
    JIRA_COMMENT = "jira_comment"
    JIRA_ATTACHMENT = "jira_attachment"


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
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ContentCategory.DOCX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ContentCategory.PPTX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ContentCategory.XLSX,
    "application/vnd.ms-excel": ContentCategory.XLSX,
}

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
    ".docx": ContentCategory.DOCX,
    ".pptx": ContentCategory.PPTX,
    ".xlsx": ContentCategory.XLSX,
    ".xls": ContentCategory.XLSX,
}

_SOURCE_MAP: dict[str, ContentCategory] = {
    # NOTE: 'confluence' and 'jira' are routed by content_type in classify() below.
}

# Attachment MIME → ContentCategory mapping for Confluence/Jira attachments
_ATTACHMENT_MIME_MAP: dict[str, ContentCategory] = {
    "application/pdf": ContentCategory.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ContentCategory.DOCX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ContentCategory.PPTX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ContentCategory.XLSX,
    "application/vnd.ms-excel": ContentCategory.XLSX,
    "text/csv": ContentCategory.CSV,
    "text/html": ContentCategory.HTML,
    "text/plain": ContentCategory.PLAINTEXT,
    "text/markdown": ContentCategory.MARKDOWN,
}


def classify(raw: RawDocument) -> ContentCategory:
    """Classify a RawDocument into a ContentCategory.

    Confluence and Jira documents are sub-routed by their ``content_type``
    field so that pages, comments, and attachments each get a dedicated
    extractor.  Attachments are further sub-routed by MIME type.
    """
    system = raw.source_system.lower()

    # ── Confluence sub-routing ────────────────────────────────────────
    if system == "confluence":
        ct = (raw.content_type or raw.metadata.get("content_type", "")).lower()
        if ct == "comment":
            return ContentCategory.CONFLUENCE_COMMENT
        if ct == "attachment":
            return _classify_attachment(raw)
        # page, blogpost, or unspecified → page extractor
        return ContentCategory.CONFLUENCE_PAGE

    # ── Jira sub-routing ──────────────────────────────────────────────
    if system == "jira":
        ct = (raw.content_type or raw.metadata.get("content_type", "")).lower()
        if ct == "comment":
            return ContentCategory.JIRA_COMMENT
        if ct == "attachment":
            return _classify_attachment(raw)
        return ContentCategory.JIRA_ISSUE

    # ── Other source systems ──────────────────────────────────────────
    if system in _SOURCE_MAP:
        return _SOURCE_MAP[system]

    mime = raw.mime_type.lower().strip() if raw.mime_type else ""
    if mime in _MIME_MAP:
        return _MIME_MAP[mime]
    if mime.startswith("image/"):
        return ContentCategory.IMAGE

    uri = raw.source_uri or ""
    clean_uri = uri.split("?")[0].split("#")[0]
    ext = ""
    if "." in clean_uri:
        ext = "." + clean_uri.rsplit(".", 1)[-1].lower()
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]

    if raw.raw_html:
        return ContentCategory.HTML
    content_head = (raw.raw_content or "")[:500]
    if content_head.lstrip().startswith(("<html", "<!DOCTYPE", "<div", "<table")):
        return ContentCategory.HTML
    if raw.binary_content and raw.binary_content[:4] == b"%PDF":
        return ContentCategory.PDF

    return ContentCategory.PLAINTEXT


def _classify_attachment(raw: RawDocument) -> ContentCategory:
    """Sub-classify an attachment by MIME type or filename extension.

    Falls back to IMAGE (for VLM) or BINARY if type is unknown.
    """
    mime = (raw.mime_type or raw.metadata.get("media_type", "")).lower().strip()

    # Check MIME map first
    if mime in _ATTACHMENT_MIME_MAP:
        return _ATTACHMENT_MIME_MAP[mime]
    if mime.startswith("image/"):
        return ContentCategory.IMAGE

    # Fallback: guess from filename extension
    filename = raw.metadata.get("filename", raw.title or "")
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext in _EXT_MAP:
            return _EXT_MAP[ext]

    return ContentCategory.BINARY


class InputRouter:
    """Route RawDocuments to the appropriate extractor."""

    def __init__(self, routing_table: dict[ContentCategory, BaseExtractor]):
        self._table = routing_table

    def route(self, raw: RawDocument) -> tuple[ContentCategory, BaseExtractor | None]:
        category = classify(raw)
        extractor = self._table.get(category)
        if extractor is None:
            log.warning("No extractor for category=%s (uri=%s, mime=%s)", category.value, raw.source_uri, raw.mime_type)
        return category, extractor

    @property
    def categories(self) -> list[ContentCategory]:
        return list(self._table.keys())
