"""Jira issue extractor.

Parses Jira issue descriptions (wiki markup or ADF) and rendered HTML
into structured ``ContentBlock``s. Comments are extracted as separate
documents by the adapter, NOT inlined into the issue.
"""

from __future__ import annotations

import html as html_mod
import re

from pipeline.adapters.base import RawDocument
from pipeline.schemas.blocks import (
    CodeBlock,
    ContentBlock,
    HeadingBlock,
    LinkRef,
    ListBlock,
    TextBlock,
)
from pipeline.schemas.canonical import CanonicalDocument

from .base import BaseExtractor, build_sections


class JiraIssueExtractor(BaseExtractor):
    """Extract content from a Jira issue or comment."""

    name = "jira_issue_extractor"

    def can_handle(self, raw: RawDocument) -> bool:
        return raw.source_system == "jira"

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        content_type = raw.content_type or raw.metadata.get("content_type", "issue")
        meta = dict(raw.metadata)

        if content_type == "comment":
            return self._extract_comment(raw, meta)
        return self._extract_issue(raw, meta)

    def _extract_issue(self, raw: RawDocument, meta: dict) -> CanonicalDocument:
        """Extract an issue description into blocks."""
        description = raw.raw_content or raw.raw_html or ""
        blocks, links = self._parse_description(description)

        # Prepend a header block with issue metadata
        issue_key = meta.get("issue_key", raw.source_id)
        status = meta.get("status", "")
        issue_type = meta.get("issue_type", "")
        priority = meta.get("priority", "")

        header_parts = [f"[{issue_key}]"]
        if issue_type:
            header_parts.append(issue_type)
        if status:
            header_parts.append(f"Status: {status}")
        if priority:
            header_parts.append(f"Priority: {priority}")

        blocks.insert(0, HeadingBlock(content=raw.title, level=1))
        if len(header_parts) > 1:
            blocks.insert(1, TextBlock(content=" | ".join(header_parts)))

        sections = build_sections(blocks)

        return CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="issue",
            source_content_type="issue",
            content_blocks=blocks,
            section_hierarchy=sections,
            links=links,
            metadata=meta,
        )

    def _extract_comment(self, raw: RawDocument, meta: dict) -> CanonicalDocument:
        """Extract a Jira comment into blocks."""
        text = raw.raw_content or raw.raw_html or ""
        blocks = self._parse_comment(text)

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

    def _parse_description(
        self, text: str
    ) -> tuple[list[ContentBlock], list[LinkRef]]:
        """Parse Jira description — handles both wiki markup and HTML."""
        # If it looks like HTML, parse as HTML
        if "<" in text[:100] and ("</p>" in text or "</div>" in text):
            return self._parse_html(text)
        # Otherwise parse as Jira wiki markup
        return self._parse_wiki_markup(text)

    def _parse_wiki_markup(
        self, text: str
    ) -> tuple[list[ContentBlock], list[LinkRef]]:
        blocks: list[ContentBlock] = []
        links: list[LinkRef] = []
        current_text: list[str] = []

        def flush():
            if current_text:
                content = "\n".join(current_text).strip()
                if content:
                    blocks.append(TextBlock(content=content))
                current_text.clear()

        in_code = False
        code_lines: list[str] = []

        for line in text.split("\n"):
            # Code blocks: {code} ... {code} or {noformat} ... {noformat}
            if re.match(r"\{(code|noformat)", line.strip()):
                if in_code:
                    flush()
                    blocks.append(CodeBlock(content="\n".join(code_lines)))
                    code_lines.clear()
                    in_code = False
                else:
                    flush()
                    in_code = True
                continue
            if in_code:
                code_lines.append(line)
                continue

            # Headings: h1. h2. etc.
            hm = re.match(r"^h(\d)\.\s+(.+)$", line)
            if hm:
                flush()
                blocks.append(HeadingBlock(content=hm.group(2).strip(), level=int(hm.group(1))))
                continue

            # List items: * item, ** item, # item
            if re.match(r"^[*#]+\s+", line):
                flush()
                items = [re.sub(r"^[*#]+\s+", "", line).strip()]
                blocks.append(ListBlock(items=items, ordered=line.startswith("#")))
                continue

            # Links: [text|url] or [url]
            for m in re.finditer(r"\[([^|]*)\|([^\]]+)\]", line):
                links.append(LinkRef(url=m.group(2), text=m.group(1)))

            current_text.append(line)

        flush()
        return blocks, links

    def _parse_html(
        self, html: str
    ) -> tuple[list[ContentBlock], list[LinkRef]]:
        blocks: list[ContentBlock] = []
        links: list[LinkRef] = []

        for m in re.finditer(r"<h(\d)[^>]*>(.*?)</h\d>", html, re.DOTALL | re.IGNORECASE):
            level = int(m.group(1))
            text = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(2)).strip())
            if text:
                blocks.append(HeadingBlock(content=text, level=level))

        for m in re.finditer(r"<(ul|ol)[^>]*>(.*?)</\1>", html, re.DOTALL | re.IGNORECASE):
            ordered = m.group(1).lower() == "ol"
            items = [
                html_mod.unescape(re.sub(r"<[^>]+>", "", li.group(1)).strip())
                for li in re.finditer(r"<li[^>]*>(.*?)</li>", m.group(2), re.DOTALL | re.IGNORECASE)
            ]
            if items:
                blocks.append(ListBlock(items=[i for i in items if i], ordered=ordered))

        for m in re.finditer(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE):
            links.append(LinkRef(url=m.group(1), text=re.sub(r"<[^>]+>", "", m.group(2)).strip()))

        # Remaining text
        clean = re.sub(r"<(ul|ol|h\d)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        clean = html_mod.unescape(re.sub(r"<[^>]+>", " ", clean).strip())
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean:
            blocks.append(TextBlock(content=clean))

        return blocks, links

    def _parse_comment(self, text: str) -> list[ContentBlock]:
        if "<" in text[:100] and ("</p>" in text or "</div>" in text):
            blocks, _ = self._parse_html(text)
            return blocks
        blocks, _ = self._parse_wiki_markup(text)
        return blocks
