from __future__ import annotations

import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

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
from pipeline.storage import ArtifactStore, create_artifact_store
from .base import BaseExtractor, build_sections

log = logging.getLogger("finx-data.extractor.docling")

_MIME_EXT = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/html": ".html",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
}

_HANDLED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

_HANDLED_EXTS = {"pdf", "docx", "pptx", "xlsx", "xls", "png", "jpg", "jpeg", "tiff"}


class DoclingExtractor(BaseExtractor):
    """Extract structured content using Docling's native DoclingDocument API."""

    name = "docling_extractor"

    def __init__(self, artifact_store: ArtifactStore | None = None):
        self.artifact_store = artifact_store or create_artifact_store()
        artifacts_path = os.getenv("DOCLING_ARTIFACTS_PATH")
        pipeline_options = PdfPipelineOptions(do_table_structure=True)
        if artifacts_path:
            pipeline_options.artifacts_path = artifacts_path
        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    def can_handle(self, raw: RawDocument) -> bool:
        mime = (raw.mime_type or "").lower()
        if mime in _HANDLED_MIMES or mime.startswith("image/"):
            return True
        uri = raw.source_uri or ""
        ext = uri.rsplit(".", 1)[-1].lower() if "." in uri else ""
        return ext in _HANDLED_EXTS

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        try:
            blocks, links = self._convert(raw)
        except Exception as exc:
            log.warning("Docling conversion failed for %s: %s", raw.source_uri, exc)
            return self._fallback(raw)

        # VLM fallback for scanned PDFs: if Docling extracted very little
        # text, try OCR via vision LLM
        is_pdf = (raw.mime_type or "").lower() == "application/pdf" or (raw.source_uri or "").lower().endswith(".pdf")
        if is_pdf and self._is_scanned(blocks):
            vlm_blocks = self._vlm_ocr_fallback(raw)
            if vlm_blocks:
                blocks = vlm_blocks
                log.info("VLM OCR fallback used for scanned PDF: %s", raw.source_uri)

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

    def _convert(self, raw: RawDocument) -> tuple[list[ContentBlock], list[LinkRef]]:
        """Run Docling and map native items to ContentBlocks."""
        result = self._run_converter(raw)
        docling_doc = result.document

        blocks: list[ContentBlock] = []
        links: list[LinkRef] = []
        pending_list_items: list[str] = []
        pending_list_ordered = False

        def flush_list():
            if pending_list_items:
                blocks.append(ListBlock(items=list(pending_list_items), ordered=pending_list_ordered))
                pending_list_items.clear()

        from docling_core.types.doc.document import (
            CodeItem,
            ListItem as DoclingListItem,
            PictureItem,
            SectionHeaderItem,
            TableItem,
        )

        for item, _ in docling_doc.iterate_items():
            if isinstance(item, SectionHeaderItem):
                flush_list()
                blocks.append(HeadingBlock(content=item.text, level=item.level))
                continue

            if isinstance(item, DoclingListItem):
                if not pending_list_items:
                    pending_list_ordered = item.enumerated
                pending_list_items.append(item.text)
                continue
            else:
                flush_list()

            if isinstance(item, TableItem):
                table_block = self._extract_table(item, docling_doc)
                if table_block:
                    blocks.append(table_block)
                continue

            if isinstance(item, PictureItem):
                img = self._extract_image(item)
                if img:
                    blocks.append(img)
                continue

            if isinstance(item, CodeItem):
                blocks.append(CodeBlock(content=item.text, language=item.code_language))
                continue

            text = getattr(item, "text", "")
            if text and text.strip():
                blocks.append(TextBlock(content=text.strip()))
                hyperlink = getattr(item, "hyperlink", None)
                if hyperlink:
                    links.append(LinkRef(url=str(hyperlink), text=text.strip()))

        flush_list()
        return blocks, links

    def _run_converter(self, raw: RawDocument):
        """Convert a RawDocument using DocumentConverter."""
        binary = raw.binary_content

        # Load from artifact store if no in-memory content
        if not binary and not raw.raw_content:
            artifact_uri = raw.metadata.get("artifact_uri", "")
            if artifact_uri and self.artifact_store.exists(artifact_uri):
                binary = self.artifact_store.load(artifact_uri)
                log.debug("Loaded %d bytes from artifact store: %s", len(binary), artifact_uri)

        if binary:
            ext = _MIME_EXT.get((raw.mime_type or "").lower()) \
                or self._ext_from_uri(raw.metadata.get("filename", "")) \
                or self._ext_from_uri(raw.source_uri)
            source = DocumentStream(name=f"doc{ext}", stream=BytesIO(binary))
            return self._converter.convert(source)

        if raw.raw_content:
            ext = _MIME_EXT.get((raw.mime_type or "").lower()) or ".txt"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, mode="w") as f:
                f.write(raw.raw_content)
                tmp_path = f.name
            try:
                return self._converter.convert(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        raise ValueError("RawDocument has no content")

    def _extract_table(self, item, docling_doc) -> TableBlock | None:
        data = getattr(item, "data", None)
        if not data:
            return None

        grid = data.grid
        if not grid or len(grid) == 0:
            return None

        headers = [cell.text for cell in grid[0]]
        rows = [[cell.text for cell in row] for row in grid[1:]]
        md = item.export_to_markdown(docling_doc)
        caption = self._get_caption(item, docling_doc)
        return TableBlock(headers=headers, rows=rows, markdown=md, caption=caption)

    def _extract_image(self, item) -> ImageBlock | None:
        image_ref = getattr(item, "image", None)
        src = str(image_ref.uri) if image_ref and hasattr(image_ref, "uri") else ""
        alt = self._get_caption(item) or ""
        return ImageBlock(src=src, alt_text=alt)

    @staticmethod
    def _get_caption(item, docling_doc=None) -> str:
        captions = getattr(item, "captions", None)
        if not captions:
            return ""
        first = captions[0]
        if docling_doc and hasattr(first, "resolve"):
            resolved = first.resolve(docling_doc)
            return getattr(resolved, "text", "")
        return getattr(first, "text", str(first))

    def _is_scanned(self, blocks: list[ContentBlock]) -> bool:
        """Detect if Docling produced very little text (likely a scanned PDF)."""
        total_chars = 0
        for block in blocks:
            text = getattr(block, "content", "") or getattr(block, "markdown", "")
            total_chars += len(text)
        # If less than 50 chars total, likely scanned
        return total_chars < 50

    def _vlm_ocr_fallback(self, raw: RawDocument) -> list[ContentBlock]:
        """Try OCR via VLM for scanned PDFs."""
        try:
            import asyncio
            from pipeline.extractors.vlm import VLMService

            image_bytes = raw.binary_content
            if not image_bytes:
                artifact_uri = raw.metadata.get("artifact_uri", "")
                if artifact_uri:
                    from pipeline.storage import create_artifact_store
                    store = create_artifact_store()
                    if store.exists(artifact_uri):
                        image_bytes = store.load(artifact_uri)

            if not image_bytes:
                return []

            vlm = VLMService()
            result = asyncio.run(vlm.ocr_page(image_bytes, "application/pdf"))

            blocks: list[ContentBlock] = []
            text = result.get("text", "")
            if text and text.strip():
                blocks.append(TextBlock(content=text.strip()))

            tables = result.get("tables", [])
            for table_md in tables:
                if table_md and table_md.strip():
                    blocks.append(TableBlock(markdown=table_md))

            return blocks
        except Exception as exc:
            log.debug("VLM OCR fallback failed: %s", exc)
            return []

    def _fallback(self, raw: RawDocument) -> CanonicalDocument:
        content = raw.raw_content or ""
        blocks: list[ContentBlock] = [TextBlock(content=content)] if content else []
        return CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="document",
            content_blocks=blocks,
            metadata=raw.metadata,
        )

    @staticmethod
    def _ext_from_uri(uri: str) -> str:
        if "." in (uri or ""):
            return "." + uri.rsplit(".", 1)[-1].lower()
        return ".bin"
