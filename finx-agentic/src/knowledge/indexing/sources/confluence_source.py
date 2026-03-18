"""Confluence JSON data source — reads finx-data/output/confluence/*.json.

Structured pages (with typed items) → deterministic + LLM extraction.
Unstructured pages (raw text only) → LLM extraction only.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from scripts.bootstrap.schemas import ConfluenceFile, ConfluenceItem
from src.knowledge.graph.models import Chunk, NodeData, NodeLabel

from ..base import BaseSource, RawDocument

logger = logging.getLogger(__name__)


class ConfluenceSource(BaseSource):
    """``BaseSource`` implementation for ``finx-data/output/confluence/*.json``."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    @property
    def source_id(self) -> str:
        return "confluence"

    def discover(self) -> Iterator[RawDocument]:
        confluence_dir = self._data_dir / "confluence"
        if not confluence_dir.exists():
            logger.warning("Confluence directory not found: %s", confluence_dir)
            return

        for path in sorted(confluence_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                raw["file_path"] = str(path)
                cf = ConfluenceFile.model_validate(raw)

                yield RawDocument(
                    doc_id=cf.page_id or path.stem,
                    content=cf,
                    file_path=str(path),
                    metadata={"title": cf.title, "space": cf.space, "url": cf.url},
                )
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", path.name, exc)

    def to_chunks(self, doc: RawDocument) -> list[Chunk]:
        """Convert confluence page to chunks for LLM extraction."""
        cf: ConfluenceFile = doc.content
        chunks: list[Chunk] = []

        if cf.is_structured:
            # Structured page — serialise items as text
            for item in cf.items:
                text = self._item_to_text(item, cf)
                if text:
                    chunks.append(Chunk(
                        id=Chunk.make_id(text),
                        content=text,
                        source_id=self.source_id,
                        file_path=doc.file_path,
                        doc_id=doc.doc_id,
                    ))
        else:
            # Unstructured page — send full title + items as one chunk
            text = self._page_to_text(cf)
            if text:
                chunks.append(Chunk(
                    id=Chunk.make_id(text),
                    content=text,
                    source_id=self.source_id,
                    file_path=doc.file_path,
                    doc_id=doc.doc_id,
                ))

        return chunks

    def deterministic_upserts(self, doc: RawDocument) -> list[NodeData]:
        """Upsert known entities from structured confluence items — no LLM needed."""
        cf: ConfluenceFile = doc.content
        nodes: list[NodeData] = []

        for item in cf.items:
            name = item.display_name
            if not name:
                continue

            label = self._item_type_to_label(item.entity_type)
            if not label:
                continue

            nodes.append(NodeData(
                name=name.upper().strip(),
                label=label,
                description=item.effective_definition or item.description or "",
                domain=item.domain or "",
                synonyms=item.synonyms or [],
                tags=item.tags or [],
                source_ids=[doc.doc_id],
                file_path=doc.file_path,
                extra={
                    "source_document": cf.title,
                    "source_url": cf.url,
                },
            ))

        return [n for n in nodes if n.name]

    # ── internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _item_to_text(item: ConfluenceItem, cf: ConfluenceFile) -> str:
        """Serialise a single structured item as readable text for LLM."""
        parts: list[str] = []
        parts.append(f"Entity type: {item.entity_type}")
        parts.append(f"Name: {item.display_name}")
        if item.domain:
            parts.append(f"Domain: {item.domain}")
        if item.definition:
            parts.append(f"Definition: {item.definition}")
        if item.description and item.description != item.definition:
            parts.append(f"Description: {item.description}")
        if item.synonyms:
            parts.append(f"Synonyms: {', '.join(item.synonyms)}")
        if item.relationships:
            for rel in item.relationships:
                parts.append(
                    f"Relationship: {rel.get('edge_type', '')} → "
                    f"{rel.get('target_type', '')}: {rel.get('target_name', '')}"
                )
        parts.append(f"Source: {cf.title} ({cf.url})")
        return "\n".join(parts)

    @staticmethod
    def _page_to_text(cf: ConfluenceFile) -> str:
        """Serialise an unstructured page as a single text block."""
        parts: list[str] = [f"Page: {cf.title}"]
        if cf.space:
            parts.append(f"Space: {cf.space}")
        if cf.url:
            parts.append(f"URL: {cf.url}")
        for item in cf.items:
            name = item.display_name
            if name:
                parts.append(f"- {item.entity_type}: {name}")
                if item.description:
                    parts.append(f"  {item.description}")
        return "\n".join(parts) if len(parts) > 2 else ""

    @staticmethod
    def _item_type_to_label(entity_type: str) -> str | None:
        mapping = {
            "BusinessTerm": NodeLabel.BUSINESS_TERM.value,
            "SourceAuthority": NodeLabel.SOURCE_AUTHORITY.value,
            "UserRole": NodeLabel.USER_ROLE.value,
            "Table": NodeLabel.TABLE.value,
            "Dataset": NodeLabel.DATASET.value,
            "Metric": NodeLabel.METRIC.value,
            "Dimension": NodeLabel.DIMENSION.value,
        }
        return mapping.get(entity_type)
