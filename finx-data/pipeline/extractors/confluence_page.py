"""Confluence page / blog post extractor.

Parses Confluence ``body.storage`` HTML into structured ``ContentBlock``s
with enhanced handling for Confluence-specific macros (code, panel, info,
warning, expand, toc), internal page links, and heading hierarchy.

Optionally uses ``body.export_view`` as a cleaner text extraction source
when available in ``metadata["body_export_view"]``.
"""

from __future__ import annotations

import html as html_mod
import re
from typing import Any

from pipeline.adapters.base import RawDocument
from pipeline.schemas.blocks import (
    CodeBlock,
    ContentBlock,
    HeadingBlock,
    ImageBlock,
    LinkRef,
    ListBlock,
    TableBlock,
    TextBlock,
)
from pipeline.schemas.canonical import CanonicalDocument

from .base import BaseExtractor, build_sections

# Confluence storage format macro patterns
_MACRO_CODE = re.compile(
    r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
    r"<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>"
    r".*?</ac:structured-macro>",
    re.DOTALL | re.IGNORECASE,
)
_MACRO_PANEL = re.compile(
    r'<ac:structured-macro[^>]*ac:name="(panel|info|note|warning|tip|expand)"[^>]*>'
    r"(.*?)</ac:structured-macro>",
    re.DOTALL | re.IGNORECASE,
)
_MACRO_TOC = re.compile(
    r'<ac:structured-macro[^>]*ac:name="toc"[^>]*>.*?</ac:structured-macro>',
    re.DOTALL | re.IGNORECASE,
)
_MACRO_NOFORMAT = re.compile(
    r'<ac:structured-macro[^>]*ac:name="noformat"[^>]*>.*?'
    r"<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>"
    r".*?</ac:structured-macro>",
    re.DOTALL | re.IGNORECASE,
)

# User mention / emoticon noise
_USER_MENTION = re.compile(r"<ac:link><ri:user[^/]*/></ac:link>", re.IGNORECASE)
_EMOTICON = re.compile(r"<ac:emoticon[^/]*/?>", re.IGNORECASE)

# Internal page link
_PAGE_LINK = re.compile(
    r'<ac:link>\s*<ri:page\s+ri:content-title="([^"]*)"'
    r'(?:\s+ri:space-key="([^"]*)")?\s*/>\s*'
    r"(?:<ac:plain-text-link-body>\s*<!\[CDATA\[(.*?)\]\]>"
    r"\s*</ac:plain-text-link-body>)?\s*</ac:link>",
    re.DOTALL | re.IGNORECASE,
)

# Image attachment
_IMAGE_ATTACHMENT = re.compile(
    r'<ac:image[^>]*>\s*<ri:attachment\s+ri:filename="([^"]*)"[^/]*/>\s*</ac:image>',
    re.IGNORECASE,
)


class ConfluencePageExtractor(BaseExtractor):
    """Extract content blocks from a Confluence page or blog post.

    Handles ``body.storage`` HTML with Confluence-specific macros.
    """

    name = "confluence_page_extractor"

    def can_handle(self, raw: RawDocument) -> bool:
        return (
            raw.source_system == "confluence"
            and raw.content_type in ("page", "blogpost", "")
        )

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        html = raw.raw_html or raw.raw_content
        blocks, links = self._parse_confluence_html(html)
        sections = build_sections(blocks)

        meta = dict(raw.metadata)
        content_type = raw.content_type or meta.get("content_type", "page")

        return CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="document",
            source_content_type=content_type,
            parent_document_id=raw.parent_id,
            version=raw.version or meta.get("version", 0),
            content_blocks=blocks,
            section_hierarchy=sections,
            links=links,
            metadata=meta,
        )

    def _parse_confluence_html(
        self, html: str
    ) -> tuple[list[ContentBlock], list[LinkRef]]:
        blocks: list[ContentBlock] = []
        links: list[LinkRef] = []

        # ── Pre-extract macros before stripping tags ─────────────────

        # Code macros → CodeBlock
        for m in _MACRO_CODE.finditer(html):
            code = m.group(1).strip()
            # Try to extract language from macro params
            lang_m = re.search(r'ac:name="language"[^>]*>([^<]+)', m.group(0))
            lang = lang_m.group(1).strip() if lang_m else None
            if code:
                blocks.append(CodeBlock(content=code, language=lang))

        # Noformat macros → CodeBlock (plain text)
        for m in _MACRO_NOFORMAT.finditer(html):
            text = m.group(1).strip()
            if text:
                blocks.append(CodeBlock(content=text, language=None))

        # Panel/info/note/warning/tip macros → TextBlock with prefix
        for m in _MACRO_PANEL.finditer(html):
            macro_type = m.group(1).lower()
            inner_html = m.group(2)
            inner_text = _strip_tags(inner_html).strip()
            if inner_text:
                prefix = f"[{macro_type.upper()}] " if macro_type != "panel" else ""
                blocks.append(TextBlock(content=f"{prefix}{inner_text}"))

        # Internal page links → LinkRef
        for m in _PAGE_LINK.finditer(html):
            page_title = m.group(1)
            space_key = m.group(2) or ""
            link_text = m.group(3) or page_title
            links.append(LinkRef(
                url=f"confluence://page/{space_key}/{page_title}",
                text=link_text,
                context=f"Internal link to page: {page_title}",
            ))

        # Image attachments → ImageBlock
        for m in _IMAGE_ATTACHMENT.finditer(html):
            filename = m.group(1)
            blocks.append(ImageBlock(
                src=f"attachment://{filename}",
                alt_text=filename,
            ))

        # ── Strip macros and noise from HTML before parsing structure ─

        clean_html = html
        # Remove already-extracted code macros
        clean_html = _MACRO_CODE.sub("", clean_html)
        clean_html = _MACRO_NOFORMAT.sub("", clean_html)
        # Remove panels (already extracted)
        clean_html = _MACRO_PANEL.sub("", clean_html)
        # Remove TOC macro (navigation noise)
        clean_html = _MACRO_TOC.sub("", clean_html)
        # Remove user mentions and emoticons
        clean_html = _USER_MENTION.sub("", clean_html)
        clean_html = _EMOTICON.sub("", clean_html)
        # Remove page links (already extracted)
        clean_html = _PAGE_LINK.sub(lambda m: m.group(3) or m.group(1) or "", clean_html)
        # Remove image tags (already extracted)
        clean_html = _IMAGE_ATTACHMENT.sub("", clean_html)
        # Remove any remaining ac:* tags
        clean_html = re.sub(r"</?ac:[^>]*>", "", clean_html)
        clean_html = re.sub(r"</?ri:[^>]*>", "", clean_html)

        # ── Parse standard HTML structure ────────────────────────────

        # Tables
        for m in re.finditer(r"<table[^>]*>(.*?)</table>", clean_html, re.DOTALL | re.IGNORECASE):
            headers, rows = _parse_html_table(m.group(1))
            if headers or rows:
                md = _table_to_markdown(headers, rows)
                blocks.append(TableBlock(headers=headers, rows=rows, markdown=md))

        # Headings
        for m in re.finditer(r"<h(\d)[^>]*>(.*?)</h\d>", clean_html, re.DOTALL | re.IGNORECASE):
            level = int(m.group(1))
            text = _strip_tags(m.group(2)).strip()
            if text:
                blocks.append(HeadingBlock(content=text, level=level))

        # Lists
        for m in re.finditer(r"<(ul|ol)[^>]*>(.*?)</\1>", clean_html, re.DOTALL | re.IGNORECASE):
            ordered = m.group(1).lower() == "ol"
            items = [
                _strip_tags(li.group(1)).strip()
                for li in re.finditer(r"<li[^>]*>(.*?)</li>", m.group(2), re.DOTALL | re.IGNORECASE)
            ]
            items = [i for i in items if i]
            if items:
                blocks.append(ListBlock(items=items, ordered=ordered))

        # External links
        for m in re.finditer(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', clean_html, re.DOTALL | re.IGNORECASE):
            url = m.group(1)
            text = _strip_tags(m.group(2)).strip()
            if url and not url.startswith("confluence://"):
                links.append(LinkRef(url=url, text=text))

        # Remaining text content (strip tables, lists, headings)
        remaining = clean_html
        remaining = re.sub(r"<table[^>]*>.*?</table>", "", remaining, flags=re.DOTALL | re.IGNORECASE)
        remaining = re.sub(r"<(ul|ol)[^>]*>.*?</\1>", "", remaining, flags=re.DOTALL | re.IGNORECASE)
        remaining = re.sub(r"<h\d[^>]*>.*?</h\d>", "", remaining, flags=re.DOTALL | re.IGNORECASE)

        # Split remaining text by <p> or <br/> to get paragraph blocks
        paragraphs = re.split(r"</?p[^>]*>|<br\s*/?>", remaining)
        for p in paragraphs:
            text = _strip_tags(p).strip()
            if text and len(text) > 5:
                blocks.append(TextBlock(content=text))

        return blocks, links


# ── helpers ───────────────────────────────────────────────────────────────────


def _strip_tags(html: str) -> str:
    """Remove HTML tags and decode entities."""
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", html)).strip()


def _parse_html_table(table_html: str) -> tuple[list[str], list[list[str]]]:
    headers: list[str] = []
    rows: list[list[str]] = []
    for m in re.finditer(r"<th[^>]*>(.*?)</th>", table_html, re.DOTALL | re.IGNORECASE):
        headers.append(_strip_tags(m.group(1)))
    for tr_m in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE):
        cells = [
            _strip_tags(m.group(1))
            for m in re.finditer(r"<td[^>]*>(.*?)</td>", tr_m.group(1), re.DOTALL | re.IGNORECASE)
        ]
        if cells:
            rows.append(cells)
    return headers, rows


def _table_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    if not headers and not rows:
        return ""
    if not headers and rows:
        headers = [f"col_{i}" for i in range(len(rows[0]))]
    lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        lines.append(" | ".join(padded[: len(headers)]))
    return "\n".join(lines)
