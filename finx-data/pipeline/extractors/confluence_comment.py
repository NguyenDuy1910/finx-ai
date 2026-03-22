"""Confluence comment extractor.

Parses comment HTML (typically simpler than page body) into
``ContentBlock``s while preserving comment-specific metadata like
comment type (inline/footer), parent content ID, and author.
"""

from __future__ import annotations

import html as html_mod
import re

from pipeline.adapters.base import RawDocument
from pipeline.schemas.blocks import ContentBlock, LinkRef, TextBlock
from pipeline.schemas.canonical import CanonicalDocument

from .base import BaseExtractor


class ConfluenceCommentExtractor(BaseExtractor):
    """Extract content from a Confluence comment."""

    name = "confluence_comment_extractor"

    def can_handle(self, raw: RawDocument) -> bool:
        return (
            raw.source_system == "confluence"
            and raw.content_type == "comment"
        )

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        html = raw.raw_html or raw.raw_content
        blocks = self._parse_comment_html(html)
        meta = dict(raw.metadata)

        return CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="comment",
            source_content_type="comment",
            parent_document_id=raw.parent_id,
            content_blocks=blocks,
            section_hierarchy=[],
            links=[],
            metadata=meta,
        )

    def _parse_comment_html(self, html: str) -> list[ContentBlock]:
        """Parse comment body — comments are usually simple HTML."""
        if not html:
            return []

        # Strip Confluence macro tags
        clean = re.sub(r"</?ac:[^>]*>", "", html)
        clean = re.sub(r"</?ri:[^>]*>", "", clean)

        # Split by paragraphs
        parts = re.split(r"</?p[^>]*>|<br\s*/?>", clean)
        blocks: list[ContentBlock] = []

        for part in parts:
            text = html_mod.unescape(re.sub(r"<[^>]+>", " ", part)).strip()
            if text:
                blocks.append(TextBlock(content=text))

        return blocks
