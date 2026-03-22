"""HTML / Markdown content extractors."""

from __future__ import annotations

import html as html_mod
import re

from pipeline.adapters.base import RawDocument
from pipeline.schemas.blocks import (
    CodeBlock,
    ContentBlock,
    HeadingBlock,
    ImageBlock,
    LinkRef,
    TableBlock,
    TextBlock,
)
from pipeline.schemas.canonical import CanonicalDocument
from .base import BaseExtractor, build_sections


class HTMLExtractor(BaseExtractor):
    name = "html_extractor"

    def can_handle(self, raw: RawDocument) -> bool:
        return bool(raw.raw_html) or "<" in raw.raw_content[:500]

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        html = raw.raw_html or raw.raw_content
        blocks, links = self._parse_html(html)
        sections = build_sections(blocks)
        return CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="document",
            content_blocks=blocks,
            section_hierarchy=sections,
            links=links,
            metadata=raw.metadata,
        )

    def _parse_html(self, html: str) -> tuple[list[ContentBlock], list[LinkRef]]:
        blocks: list[ContentBlock] = []
        links: list[LinkRef] = []

        for m in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE):
            headers, rows = self._parse_html_table(m.group(1))
            md = self._table_to_markdown(headers, rows)
            blocks.append(TableBlock(headers=headers, rows=rows, markdown=md))

        for m in re.finditer(r"<h(\d)[^>]*>(.*?)</h\d>", html, re.DOTALL | re.IGNORECASE):
            level = int(m.group(1))
            text = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(2)).strip())
            if text:
                blocks.append(HeadingBlock(content=text, level=level))

        for m in re.finditer(r"<code[^>]*>(.*?)</code>", html, re.DOTALL | re.IGNORECASE):
            code = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip())
            if code:
                blocks.append(CodeBlock(content=code))

        for m in re.finditer(r'<img[^>]+src="([^"]*)"[^>]*/?>',html, re.IGNORECASE):
            src = m.group(1)
            alt_m = re.search(r'alt="([^"]*)"', m.group(0), re.IGNORECASE)
            alt = alt_m.group(1) if alt_m else ""
            blocks.append(ImageBlock(src=src, alt_text=alt))

        for m in re.finditer(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE):
            url = m.group(1)
            text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            links.append(LinkRef(url=url, text=text))

        clean = re.sub(r"<(table|code|pre)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = html_mod.unescape(re.sub(r"\s+", " ", clean).strip())
        if clean:
            blocks.append(TextBlock(content=clean))

        return blocks, links

    def _parse_html_table(self, table_html: str) -> tuple[list[str], list[list[str]]]:
        headers: list[str] = []
        rows: list[list[str]] = []
        for m in re.finditer(r"<th[^>]*>(.*?)</th>", table_html, re.DOTALL | re.IGNORECASE):
            headers.append(html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()))
        for tr_m in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE):
            cells = [
                html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip())
                for m in re.finditer(r"<td[^>]*>(.*?)</td>", tr_m.group(1), re.DOTALL | re.IGNORECASE)
            ]
            if cells:
                rows.append(cells)
        return headers, rows

    def _table_to_markdown(self, headers: list[str], rows: list[list[str]]) -> str:
        if not headers and not rows:
            return ""
        if not headers and rows:
            headers = [f"col_{i}" for i in range(len(rows[0]))]
        lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
        for row in rows:
            padded = row + [""] * (len(headers) - len(row))
            lines.append(" | ".join(padded[: len(headers)]))
        return "\n".join(lines)


class MarkdownExtractor(BaseExtractor):
    name = "markdown_extractor"

    def can_handle(self, raw: RawDocument) -> bool:
        return raw.mime_type in ("text/markdown", "text/plain") or not (
            raw.raw_html or "<" in raw.raw_content[:200]
        )

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        text = html_mod.unescape(raw.raw_content)
        blocks, links = self._parse_markdown(text)
        sections = build_sections(blocks)
        return CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="document",
            content_blocks=blocks,
            section_hierarchy=sections,
            links=links,
            metadata=raw.metadata,
        )

    def _parse_markdown(self, text: str) -> tuple[list[ContentBlock], list[LinkRef]]:
        blocks: list[ContentBlock] = []
        links: list[LinkRef] = []
        current_text: list[str] = []

        def flush_text():
            if current_text:
                content = "\n".join(current_text).strip()
                if content:
                    blocks.append(TextBlock(content=content))
                current_text.clear()

        in_code_block = False
        code_lang: str | None = None
        code_lines: list[str] = []

        for line in text.split("\n"):
            if line.strip().startswith("```"):
                if in_code_block:
                    flush_text()
                    blocks.append(CodeBlock(content="\n".join(code_lines), language=code_lang))
                    code_lines.clear()
                    in_code_block = False
                    code_lang = None
                else:
                    flush_text()
                    lang = line.strip().removeprefix("```").strip()
                    code_lang = lang if lang else None
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                flush_text()
                level = len(heading_match.group(1))
                blocks.append(HeadingBlock(content=heading_match.group(2).strip(), level=level))
                continue

            if "|" in line and re.match(r"^\s*\|", line):
                flush_text()
                table_block = self._try_parse_table(line, text)
                if table_block:
                    blocks.append(table_block)
                    continue

            for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
                links.append(LinkRef(url=m.group(2), text=m.group(1)))

            for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", line):
                flush_text()
                blocks.append(ImageBlock(src=m.group(2), alt_text=m.group(1)))

            current_text.append(line)

        flush_text()
        return blocks, links

    def _try_parse_table(self, first_line: str, full_text: str) -> TableBlock | None:
        lines = full_text.split("\n")
        table_lines: list[str] = []
        found = False
        for line in lines:
            if line.strip() == first_line.strip():
                found = True
            if found:
                if "|" in line:
                    table_lines.append(line)
                elif table_lines:
                    break

        if len(table_lines) < 2:
            return None

        def parse_row(line: str) -> list[str]:
            return [c.strip() for c in line.strip().strip("|").split("|")]

        headers = parse_row(table_lines[0])
        rows = [parse_row(l) for l in table_lines[2:] if l.strip()]
        md = "\n".join(table_lines)
        return TableBlock(headers=headers, rows=rows, markdown=md)
