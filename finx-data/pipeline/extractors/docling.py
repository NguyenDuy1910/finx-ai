"""Docling document extraction integration.

Docling (https://github.com/docling-project/docling) provides high-fidelity
document parsing for PDF, DOCX, PPTX, XLSX, HTML, and images.  It produces
a unified ``DoclingDocument`` with typed content items (texts, tables,
pictures) and hierarchical structure.

This extractor wraps Docling's ``DocumentConverter`` and maps the output
into our pipeline's ``CanonicalDocument`` format.

Docling must be installed separately::

    pip install docling

Strategy
--------
1. Binary content (PDF, DOCX, PPTX, XLSX, images) → Docling converter
2. DoclingDocument → export to Markdown → parse into typed content blocks
3. Tables exported as markdown tables preserve column headers and structure

Compared to MinerU:
- Broader format support (DOCX, PPTX, XLSX, not just PDF)
- Built-in layout model (Heron) — no external binary dependencies
- Unified DoclingDocument → Pydantic types → clean JSON/markdown export
- Native table structure with merged cell handling
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from pipeline.adapters.base import RawDocument
from pipeline.schemas.blocks import (
    CodeBlock,
    ContentBlock,
    HeadingBlock,
    ImageBlock,
    LinkRef,
    SectionNode,
    TableBlock,
    TextBlock,
)
from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.provenance import ProcessingStage, ProcessingStep, QualitySignal
from .base import BaseExtractor

log = logging.getLogger("finx-data.extractor.docling")


def _docling_available() -> bool:
    """Check if docling is installed."""
    try:
        from docling.document_converter import DocumentConverter  # noqa: F401
        return True
    except ImportError:
        return False


class DoclingExtractor(BaseExtractor):
    """Extract structured content using Docling's DocumentConverter.

    Handles: PDF, DOCX, PPTX, XLSX, images.
    Falls back to MarkdownExtractor if Docling is not installed.
    """

    name = "docling_extractor"

    def __init__(self, *, output_dir: str | Path | None = None):
        self._output_dir = Path(output_dir) if output_dir else None
        self._available = _docling_available()
        if not self._available:
            log.warning("Docling not installed. Install with: pip install docling")

    def can_handle(self, raw: RawDocument) -> bool:
        if not self._available:
            return False
        mime = (raw.mime_type or "").lower()
        # PDF, Office formats, images
        if mime in (
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            return True
        if mime.startswith("image/"):
            return True
        # Check file extension
        uri = raw.source_uri or ""
        ext = uri.rsplit(".", 1)[-1].lower() if "." in uri else ""
        return ext in ("pdf", "docx", "pptx", "xlsx", "png", "jpg", "jpeg", "tiff")

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        t0 = time.monotonic()

        if not self._available:
            # Fallback: treat as text
            return self._fallback_extract(raw, t0)

        try:
            markdown_text = self._convert_with_docling(raw)
            blocks, links = self._parse_docling_markdown(markdown_text)
        except Exception as exc:
            log.warning("Docling conversion failed for %s: %s — falling back to text", raw.source_uri, exc)
            return self._fallback_extract(raw, t0)

        sections = self._build_sections(blocks)
        quality = self._assess_quality(blocks)

        doc = CanonicalDocument(
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
        doc.provenance.add_step(
            ProcessingStep(
                stage=ProcessingStage.EXTRACTION,
                processor=self.name,
                duration_ms=(time.monotonic() - t0) * 1000,
                input_hash=raw.content_hash,
                parameters={"method": "docling"},
            )
        )
        doc.provenance.quality = quality
        return doc

    def _convert_with_docling(self, raw: RawDocument) -> str:
        """Run Docling DocumentConverter and return markdown output."""
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()

        # Write binary to temp file for Docling to read
        if raw.binary_content:
            ext = self._ext_for_mime(raw.mime_type)
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(raw.binary_content)
                tmp_path = f.name

            try:
                result = converter.convert(tmp_path)
                return result.document.export_to_markdown()
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        # For text-based content, write to temp file
        if raw.raw_content:
            ext = self._ext_for_mime(raw.mime_type) or ".txt"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, mode="w") as f:
                f.write(raw.raw_content)
                tmp_path = f.name

            try:
                result = converter.convert(tmp_path)
                return result.document.export_to_markdown()
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        return ""

    def _parse_docling_markdown(
        self, text: str
    ) -> tuple[list[ContentBlock], list[LinkRef]]:
        """Parse Docling's markdown output into typed content blocks."""
        import re

        blocks: list[ContentBlock] = []
        links: list[LinkRef] = []
        current_text: list[str] = []

        def flush_text() -> None:
            if current_text:
                content = "\n".join(current_text).strip()
                if content:
                    blocks.append(TextBlock(content=content))
                current_text.clear()

        in_code = False
        code_lines: list[str] = []
        code_lang: str | None = None

        in_table = False
        table_lines: list[str] = []

        for line in text.split("\n"):
            stripped = line.strip()

            # Code blocks
            if stripped.startswith("```"):
                if in_code:
                    flush_text()
                    blocks.append(CodeBlock(content="\n".join(code_lines), language=code_lang))
                    code_lines.clear()
                    code_lang = None
                    in_code = False
                else:
                    flush_text()
                    in_code = True
                    lang = stripped[3:].strip()
                    code_lang = lang if lang else None
                continue

            if in_code:
                code_lines.append(line)
                continue

            # Table detection (lines with pipes)
            if "|" in stripped and stripped.startswith("|"):
                if not in_table:
                    flush_text()
                    in_table = True
                    table_lines = []
                table_lines.append(stripped)
                continue
            elif in_table:
                # End of table
                self._flush_table(blocks, table_lines)
                table_lines.clear()
                in_table = False

            # Headings
            heading_m = re.match(r"^(#{1,6})\s+(.+)", stripped)
            if heading_m:
                flush_text()
                level = len(heading_m.group(1))
                blocks.append(HeadingBlock(content=heading_m.group(2).strip(), level=level))
                continue

            # Images
            img_m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
            if img_m:
                flush_text()
                blocks.append(ImageBlock(src=img_m.group(2), alt_text=img_m.group(1)))
                continue

            # Links
            for lm in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", stripped):
                links.append(LinkRef(url=lm.group(2), text=lm.group(1)))

            # Regular text
            if stripped:
                current_text.append(stripped)
            elif current_text:
                flush_text()

        # Flush remaining
        flush_text()
        if in_table and table_lines:
            self._flush_table(blocks, table_lines)

        return blocks, links

    def _flush_table(self, blocks: list[ContentBlock], lines: list[str]) -> None:
        """Parse markdown table lines into a TableBlock."""
        if len(lines) < 2:
            return

        def parse_row(line: str) -> list[str]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            return cells

        headers = parse_row(lines[0])
        # Skip separator line (---|----|---)
        rows: list[list[str]] = []
        for line in lines[2:] if len(lines) > 2 else []:
            row = parse_row(line)
            if row and not all(set(c) <= {"-", " ", ":"} for c in row):
                rows.append(row)

        markdown = "\n".join(lines)
        blocks.append(TableBlock(headers=headers, rows=rows, markdown=markdown))

    def _build_sections(self, blocks: list[ContentBlock]) -> list[SectionNode]:
        sections: list[SectionNode] = []
        current_path: list[str] = []
        for i, block in enumerate(blocks):
            if isinstance(block, HeadingBlock):
                while current_path and len(current_path) >= block.level:
                    current_path.pop()
                current_path.append(block.content)
                sections.append(SectionNode(
                    title=block.content, level=block.level,
                    path=list(current_path), block_indices=[i],
                ))
            elif sections:
                sections[-1].block_indices.append(i)
        return sections

    def _assess_quality(self, blocks: list[ContentBlock]) -> QualitySignal:
        word_count = sum(
            len(getattr(b, "content", "").split())
            for b in blocks if hasattr(b, "content")
        )
        return QualitySignal(
            word_count=word_count,
            has_tables=any(isinstance(b, TableBlock) for b in blocks),
            has_images=any(isinstance(b, ImageBlock) for b in blocks),
            has_code=any(isinstance(b, CodeBlock) for b in blocks),
        )

    def _fallback_extract(self, raw: RawDocument, t0: float) -> CanonicalDocument:
        """Simple text-based fallback when Docling is unavailable."""
        content = raw.raw_content or ""
        blocks: list[ContentBlock] = [TextBlock(content=content)] if content else []
        doc = CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="document",
            content_blocks=blocks,
            metadata=raw.metadata,
        )
        doc.provenance.add_step(
            ProcessingStep(
                stage=ProcessingStage.EXTRACTION,
                processor=self.name,
                duration_ms=(time.monotonic() - t0) * 1000,
                input_hash=raw.content_hash,
                parameters={"method": "fallback_text"},
            )
        )
        return doc

    @staticmethod
    def _ext_for_mime(mime: str) -> str:
        _map = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "text/html": ".html",
            "text/markdown": ".md",
            "text/plain": ".txt",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/tiff": ".tiff",
        }
        return _map.get(mime, ".bin")
