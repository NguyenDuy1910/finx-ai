"""MinerU document extraction integration.

MinerU (https://github.com/opendatalab/MinerU) is used for high-fidelity
extraction of complex documents (PDFs, scanned images) into structured
markdown with tables, images, and layout preservation.

This module wraps the MinerU CLI/API output into our pipeline's
``CanonicalDocument`` format.

Strategy
--------
1. Binary content (PDF, images) → MinerU CLI → structured markdown + images
2. MinerU output (markdown + metadata) → MarkdownExtractor → CanonicalDocument
3. Extracted images get ``ImageBlock`` entries with paths for downstream OCR/captioning

MinerU must be installed separately: ``pip install magic-pdf[full]``
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
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

log = logging.getLogger("finx-data.extractor.mineru")


def _mineru_available() -> bool:
    """Check if the MinerU CLI ``magic-pdf`` is on PATH."""
    try:
        result = subprocess.run(
            ["magic-pdf", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class MinerUExtractor(BaseExtractor):
    """Extract structure from PDFs and images via MinerU.

    Falls back to raw text extraction if MinerU is unavailable.
    """

    name = "mineru_extractor"

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "mineru_output"
        self._available: bool | None = None

    @property
    def is_available(self) -> bool:
        if self._available is None:
            self._available = _mineru_available()
        return self._available

    def can_handle(self, raw: RawDocument) -> bool:
        return raw.mime_type in ("application/pdf",) or (
            raw.binary_content is not None
            and raw.metadata.get("format") in ("pdf",)
        )

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        t0 = time.monotonic()

        if self.is_available and raw.binary_content:
            doc = self._extract_with_mineru(raw, t0)
        else:
            if not self.is_available:
                log.warning(
                    "MinerU not available, falling back to raw text for %s",
                    raw.source_uri,
                )
            doc = self._extract_fallback(raw, t0)

        return doc

    def _extract_with_mineru(self, raw: RawDocument, t0: float) -> CanonicalDocument:
        """Run MinerU CLI on binary content and parse the output."""
        # Write binary to temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw.binary_content)  # type: ignore[arg-type]
            tmp_path = tmp.name

        try:
            output_path = self.output_dir / raw.source_id.replace("/", "_")
            output_path.mkdir(parents=True, exist_ok=True)

            # Run MinerU
            cmd = [
                "magic-pdf",
                "-p", tmp_path,
                "-o", str(output_path),
                "-m", "auto",
            ]
            log.info("Running MinerU: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(output_path),
            )

            if result.returncode != 0:
                log.error("MinerU failed: %s", result.stderr[:500])
                return self._extract_fallback(raw, t0)

            # Parse MinerU output — look for the markdown file
            md_files = list(output_path.rglob("*.md"))
            if not md_files:
                log.warning("MinerU produced no markdown output for %s", raw.source_uri)
                return self._extract_fallback(raw, t0)

            md_content = md_files[0].read_text(encoding="utf-8", errors="replace")

            # Parse the markdown into blocks
            blocks, links = self._parse_mineru_markdown(md_content, output_path)
            sections = self._build_sections(blocks)
            quality = self._assess_quality(blocks, md_content)

            doc = CanonicalDocument(
                source_system=raw.source_system,
                source_uri=raw.source_uri,
                source_document_id=raw.source_id,
                title=raw.title,
                content_type="document",
                content_blocks=blocks,
                section_hierarchy=sections,
                links=links,
                metadata={**raw.metadata, "extractor": "mineru", "mineru_output": str(output_path)},
            )
            doc.provenance.add_step(
                ProcessingStep(
                    stage=ProcessingStage.EXTRACTION,
                    processor=self.name,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    input_hash=raw.content_hash,
                    parameters={"method": "mineru", "output_path": str(output_path)},
                )
            )
            doc.provenance.quality = quality
            return doc

        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _extract_fallback(self, raw: RawDocument, t0: float) -> CanonicalDocument:
        """Minimal fallback when MinerU is not available."""
        blocks: list[ContentBlock] = []
        if raw.raw_content:
            blocks.append(TextBlock(content=raw.raw_content))
        elif raw.binary_content:
            blocks.append(
                TextBlock(content=f"[Binary document: {raw.mime_type}, {len(raw.binary_content)} bytes]")
            )

        doc = CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="document",
            content_blocks=blocks,
            metadata={**raw.metadata, "extractor": "fallback"},
        )
        doc.provenance.add_step(
            ProcessingStep(
                stage=ProcessingStage.EXTRACTION,
                processor=f"{self.name}:fallback",
                duration_ms=(time.monotonic() - t0) * 1000,
                input_hash=raw.content_hash,
                parameters={"method": "fallback", "reason": "mineru_unavailable"},
            )
        )
        doc.provenance.quality = QualitySignal(
            extraction_confidence=0.3,
            word_count=len(raw.raw_content.split()) if raw.raw_content else 0,
            parsing_warnings=["MinerU unavailable, used fallback extraction"],
        )
        return doc

    def _parse_mineru_markdown(
        self, md_content: str, output_path: Path
    ) -> tuple[list[ContentBlock], list[LinkRef]]:
        """Parse MinerU-generated markdown into typed blocks.

        MinerU markdown has conventions:
        - Standard markdown headings
        - Tables in pipe format
        - Images referenced as ![](path)
        - Code blocks in fenced blocks
        """
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

        for line in md_content.split("\n"):
            # Code blocks
            if line.strip().startswith("```"):
                if in_code:
                    flush_text()
                    blocks.append(CodeBlock(content="\n".join(code_lines), language=code_lang))
                    code_lines.clear()
                    in_code = False
                    code_lang = None
                else:
                    flush_text()
                    if in_table:
                        self._flush_table(table_lines, blocks)
                        in_table = False
                    lang = line.strip().removeprefix("```").strip()
                    code_lang = lang or None
                    in_code = True
                continue

            if in_code:
                code_lines.append(line)
                continue

            # Table detection
            if re.match(r"^\s*\|", line):
                if not in_table:
                    flush_text()
                    in_table = True
                    table_lines = []
                table_lines.append(line)
                continue
            elif in_table:
                self._flush_table(table_lines, blocks)
                in_table = False

            # Headings
            heading_m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_m:
                flush_text()
                blocks.append(
                    HeadingBlock(
                        content=heading_m.group(2).strip(),
                        level=len(heading_m.group(1)),
                    )
                )
                continue

            # Images
            img_m = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", line)
            for alt, src in img_m:
                flush_text()
                # Resolve relative image paths against MinerU output dir
                img_path = output_path / src if not src.startswith(("http://", "https://")) else None
                resolved_src = str(img_path) if img_path and img_path.exists() else src
                blocks.append(ImageBlock(src=resolved_src, alt_text=alt))

            # Links
            for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
                if not line.strip().startswith("!"):
                    links.append(LinkRef(url=m.group(2), text=m.group(1)))

            # Regular text
            if not img_m:
                current_text.append(line)

        flush_text()
        if in_table:
            self._flush_table(table_lines, blocks)

        return blocks, links

    def _flush_table(self, lines: list[str], blocks: list[ContentBlock]) -> None:
        if len(lines) < 2:
            return

        def parse_row(line: str) -> list[str]:
            return [c.strip() for c in line.strip().strip("|").split("|")]

        headers = parse_row(lines[0])
        # Skip separator line (---) if present
        data_start = 2 if len(lines) > 1 and re.match(r"^[\s|:-]+$", lines[1]) else 1
        rows = [parse_row(l) for l in lines[data_start:] if l.strip()]
        md = "\n".join(lines)

        blocks.append(TableBlock(headers=headers, rows=rows, markdown=md))

    def _build_sections(self, blocks: list[ContentBlock]) -> list[SectionNode]:
        sections: list[SectionNode] = []
        current_path: list[str] = []

        for i, block in enumerate(blocks):
            if isinstance(block, HeadingBlock):
                while current_path and len(current_path) >= block.level:
                    current_path.pop()
                current_path.append(block.content)
                sections.append(
                    SectionNode(
                        title=block.content,
                        level=block.level,
                        path=list(current_path),
                        block_indices=[i],
                    )
                )
            elif sections:
                sections[-1].block_indices.append(i)

        return sections

    def _assess_quality(self, blocks: list[ContentBlock], raw_md: str) -> QualitySignal:
        word_count = len(raw_md.split())
        return QualitySignal(
            extraction_confidence=0.85,
            word_count=word_count,
            has_tables=any(isinstance(b, TableBlock) for b in blocks),
            has_images=any(isinstance(b, ImageBlock) for b in blocks),
            has_code=any(isinstance(b, CodeBlock) for b in blocks),
        )
