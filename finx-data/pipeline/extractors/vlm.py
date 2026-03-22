from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any

from pipeline.adapters.base import RawDocument
from pipeline.schemas.blocks import (
    BlockProvenance,
    ChartBlock,
    ContentBlock,
    DiagramBlock,
    ImageBlock,
    KeyValueBlock,
    TableBlock,
    TextBlock,
)
from pipeline.schemas.canonical import CanonicalDocument
from pipeline.storage import ArtifactStore, create_artifact_store

from .base import BaseExtractor

log = logging.getLogger("finx-data.extractor.vlm")

_VLM_MODEL = os.environ.get("VLM_MODEL", "gpt-4o")
_VLM_CONCURRENCY = int(os.environ.get("VLM_CONCURRENCY", "4"))

# ── prompts ───────────────────────────────────────────────────────────────────

_DESCRIBE_IMAGE_PROMPT = """\
You are a multimodal document extraction assistant for enterprise knowledge \
ingestion in banking and fintech.

Your task is to analyze ONE image and return a structured JSON result for \
indexing and retrieval.

## Primary goals
1. Extract all visible textual content exactly as seen.
2. Preserve document structure in reading order.
3. Detect tables, forms, screenshots, charts, diagrams, scanned documents, \
and mixed-content images.
4. Extract finance-relevant fields when clearly visible.
5. Separate direct observation from interpretation.
6. Do NOT hallucinate missing or unreadable content.

## Domain hints
This image may belong to banking / fintech / enterprise knowledge systems.
Pay special attention to:
- dates, times, currency codes and symbols
- amounts, balances, percentages, interest rates
- account numbers (including masked forms)
- transaction IDs, reference numbers, invoice numbers
- customer IDs, card numbers (masked)
- product names, fees, limits, thresholds
- chart legends and axes, dashboard labels and KPI values

## Extraction rules
- Preserve original language exactly. Do not translate.
- Keep numbers, decimals, separators, currency symbols, and negative signs \
exactly as shown.
- If text is unclear, include best effort text and list uncertainty in warnings.
- Do not invent rows/columns in tables.
- If multiple tables exist, extract all of them.
- If the image is a screenshot, ignore irrelevant browser chrome unless it \
contains meaningful business context.
- If the image contains a chart, extract chart title, axes, legend, visible \
values, and trend summary.
- If the image contains a diagram, extract components, labels, arrows, and \
relationships.
- If the image contains a form, extract visible fields as key-value pairs.
- If no text is visible, still describe the image faithfully.

## Output requirements
Return valid JSON only, using this schema:
{
  "document_type": "scan|screenshot|photo|table|chart|diagram|form|mixed|other",
  "image_type": "scan|screenshot|photo|table|chart|diagram|form|mixed|other",
  "language": "vi|en|mixed|other",
  "summary": "short factual summary of the image",
  "description": "detailed but factual description of visible content only",
  "ocr_text": "all visible text in reading order, preserving line breaks",
  "tables": [
    {
      "title": "table title if any",
      "markdown": "markdown representation of the table",
      "notes": "uncertainty or merged-cell notes if any"
    }
  ],
  "key_values": [
    {"key": "field name", "value": "field value"}
  ],
  "entities": {
    "dates": [],
    "amounts": [],
    "currencies": [],
    "percentages": [],
    "account_numbers": [],
    "transaction_ids": [],
    "organizations": [],
    "products": [],
    "people": []
  },
  "warnings": [],
  "confidence": "high|medium|low"
}

## Important constraints
- Return only information supported by the image.
- Do not guess unreadable text.
- Do not normalize or rewrite financial values.
- Prefer exact extraction over fluent prose.
"""

_OCR_PAGE_PROMPT = """\
You are an OCR assistant. Extract ALL text from this scanned document page.
Preserve the original formatting as much as possible:
- Keep headings, paragraphs, and list structure
- Reproduce tables in Markdown format
- Note any text that is unclear or partially visible

Respond in JSON format:
{
  "text": "full extracted text from the page",
  "tables": ["markdown table 1", "markdown table 2"],
  "confidence": "high|medium|low"
}
"""


class VLMService:
    """Wrapper around the vision LLM for image analysis tasks."""

    def __init__(
        self,
        model: str = _VLM_MODEL,
        concurrency: int = _VLM_CONCURRENCY,
    ) -> None:
        self.model = model
        self._sem = asyncio.Semaphore(concurrency)

    async def describe_image(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> dict[str, str]:
        """Send an image to the VLM for description + OCR."""
        b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:{mime_type};base64,{b64}"

        messages = [
            {"role": "system", "content": "You are a multimodal document extraction assistant for enterprise knowledge ingestion."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _DESCRIBE_IMAGE_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ]
        return await self._call(messages)

    async def ocr_page(self, page_image_bytes: bytes, mime_type: str = "image/png") -> dict[str, Any]:
        """OCR a scanned document page via VLM."""
        b64 = base64.b64encode(page_image_bytes).decode()
        data_uri = f"data:{mime_type};base64,{b64}"

        messages = [
            {"role": "system", "content": "You are an OCR assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _OCR_PAGE_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ]
        return await self._call(messages)

    async def _call(self, messages: list[dict]) -> dict:
        import json
        from openai import AsyncOpenAI

        _base_url = os.environ.get("NINE_ROUTER_BASE_URL", "http://localhost:20128/v1")
        _api_key = os.environ.get("NINE_ROUTER_API_KEY", "YOUR_9ROUTER_KEY")
        client = AsyncOpenAI(base_url=_base_url, api_key=_api_key)

        async with self._sem:
            try:
                resp = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or "{}"
                return json.loads(raw)
            except Exception as exc:
                log.warning("VLM call failed: %s", exc)
                return {}
            finally:
                await client.close()


class VLMExtractor(BaseExtractor):
    """Extract content from images and scanned documents using vision LLM.

    For image attachments (PNG, JPEG, TIFF, etc.):
    - Generates a detailed description
    - Extracts OCR text
    - Detects and extracts tables

    Loads binary from ``ArtifactStore`` using ``metadata["artifact_uri"]``.
    """

    name = "vlm_extractor"

    def __init__(
        self,
        artifact_store: ArtifactStore | None = None,
        vlm_service: VLMService | None = None,
    ) -> None:
        self.artifact_store = artifact_store or create_artifact_store()
        self.vlm = vlm_service or VLMService()

    def can_handle(self, raw: RawDocument) -> bool:
        mime = (raw.mime_type or "").lower()
        return mime.startswith("image/")

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        """Extract content from an image attachment."""
        blocks, block_provenance, vlm_meta = asyncio.run(self._extract_async(raw))
        meta = dict(raw.metadata)
        meta.update(vlm_meta)

        return CanonicalDocument(
            source_system=raw.source_system,
            source_uri=raw.source_uri,
            source_document_id=raw.source_id,
            title=raw.title,
            content_type="image",
            source_content_type="attachment",
            parent_document_id=raw.parent_id,
            content_blocks=blocks,
            block_provenance=block_provenance,
            section_hierarchy=[],
            links=[],
            metadata=meta,
        )

    async def _extract_async(self, raw: RawDocument) -> tuple[list[ContentBlock], list[BlockProvenance], dict]:
        blocks: list[ContentBlock] = []
        provenance: list[BlockProvenance] = []
        vlm_meta: dict = {}

        # Load binary from artifact store or raw document
        image_bytes = raw.binary_content
        if not image_bytes:
            artifact_uri = raw.metadata.get("artifact_uri", "")
            if artifact_uri and self.artifact_store.exists(artifact_uri):
                image_bytes = self.artifact_store.load(artifact_uri)

        if not image_bytes:
            log.warning("No image data for %s", raw.source_uri)
            return blocks, provenance, vlm_meta

        mime_type = raw.mime_type or "image/png"

        # Call VLM for structured extraction
        result = await self.vlm.describe_image(image_bytes, mime_type)

        description = result.get("description", "")
        summary = result.get("summary", "")
        ocr_text = result.get("ocr_text", "")
        image_type = result.get("image_type", "other")
        confidence_str = result.get("confidence", "low")
        confidence_val = {"high": 0.9, "medium": 0.7, "low": 0.4}.get(confidence_str, 0.4)

        # Store VLM metadata for downstream enrichment
        if summary:
            vlm_meta["summary"] = summary
        if result.get("language"):
            vlm_meta["language"] = result["language"]
        if result.get("document_type"):
            vlm_meta["document_type"] = result["document_type"]
        if result.get("entities"):
            vlm_meta["vlm_entities"] = result["entities"]
        if result.get("warnings"):
            vlm_meta["vlm_warnings"] = result["warnings"]
        vlm_meta["vlm_confidence"] = confidence_str

        base_prov = BlockProvenance(
            extractor="vlm_extractor",
            confidence=confidence_val,
            warnings=result.get("warnings", []),
        )

        # 1. Image block with VLM caption
        blocks.append(ImageBlock(
            src=raw.metadata.get("artifact_uri", raw.source_uri),
            alt_text=raw.title,
            description=description,
            mime_type=mime_type,
        ))
        provenance.append(base_prov)

        # 2. OCR text block
        if ocr_text and ocr_text.strip():
            blocks.append(TextBlock(content=ocr_text))
            provenance.append(base_prov.model_copy())

        # 3. Tables from structured response
        tables = result.get("tables", [])
        if tables and isinstance(tables, list):
            for tbl in tables:
                md = tbl.get("markdown", "") if isinstance(tbl, dict) else str(tbl)
                if md and md.strip():
                    blocks.append(TableBlock(markdown=md))
                    provenance.append(base_prov.model_copy())

        # 4. Key-value pairs → KeyValueBlock
        kv_pairs = result.get("key_values", [])
        if kv_pairs and isinstance(kv_pairs, list):
            valid_pairs = [
                {"key": p.get("key", ""), "value": p.get("value", "")}
                for p in kv_pairs
                if isinstance(p, dict) and p.get("key") and p.get("value")
            ]
            if valid_pairs:
                blocks.append(KeyValueBlock(
                    pairs=valid_pairs,
                    source_context=f"VLM extraction from {image_type} image",
                ))
                provenance.append(base_prov.model_copy())

        # 5. Chart data → ChartBlock (if image_type indicates chart)
        if image_type == "chart":
            blocks.append(ChartBlock(
                chart_type=result.get("chart_type", ""),
                title=result.get("chart_title", summary),
                description=description,
                trend_summary=result.get("trend_summary", ""),
            ))
            provenance.append(base_prov.model_copy())

        # 6. Diagram data → DiagramBlock (if image_type indicates diagram)
        if image_type == "diagram":
            blocks.append(DiagramBlock(
                diagram_type=result.get("diagram_type", ""),
                title=summary,
                description=description,
            ))
            provenance.append(base_prov.model_copy())

        return blocks, provenance, vlm_meta
