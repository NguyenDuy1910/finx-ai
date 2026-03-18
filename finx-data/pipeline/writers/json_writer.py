"""JSON file writer — writes canonical documents to disk.

Produces three output formats:
1. **Canonical JSON** — full CanonicalDocument serialization with provenance
2. **Legacy JSON** — backward-compatible format matching the existing output
   consumed by finx-agentic bootstrap pipeline
3. **Knowledge JSON** — Qdrant-ready flat format optimized for vector embedding
   and knowledge graph ingestion (one doc = one embedding point)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.provenance import ProcessingStage, ProcessingStep

from .base import BaseWriter

log = logging.getLogger("finx-data.writer.json")


class JSONWriter(BaseWriter):
    """Write canonical documents as JSON files."""

    name = "json_writer"

    def __init__(
        self,
        output_dir: str | Path,
        *,
        format: str = "canonical",
        overwrite: bool = False,
    ):
        """
        Parameters
        ----------
        output_dir : Path
            Root directory for JSON output.
        format : str
            'canonical' for full schema, 'legacy' for backward-compatible format.
        overwrite : bool
            Whether to overwrite existing files.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.format = format
        self.overwrite = overwrite

    def write(self, doc: CanonicalDocument) -> str:
        # Build file name from source coordinates
        safe_name = self._safe_filename(doc)
        path = self.output_dir / f"{safe_name}.json"

        if path.exists() and not self.overwrite:
            log.debug("Skipping existing file: %s", path)
            return str(path)

        if self.format == "legacy":
            data = self._to_legacy_format(doc)
        elif self.format == "knowledge":
            data = self._to_knowledge_format(doc)
        else:
            data = json.loads(doc.model_dump_json())

        # Add output provenance step
        doc.provenance.add_step(
            ProcessingStep(
                stage=ProcessingStage.OUTPUT,
                processor=self.name,
                output_hash=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
            )
        )

        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        log.debug("Wrote %s", path)
        return str(path)

    def _safe_filename(self, doc: CanonicalDocument) -> str:
        """Generate a safe, deterministic filename."""
        raw = doc.source_document_id or doc.title or doc.document_id[:16]
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in raw)

    def _to_legacy_format(self, doc: CanonicalDocument) -> dict[str, Any]:
        """Convert to the format expected by existing finx-agentic bootstrap.

        For Confluence pages: {page_id, title, url, space, items: [...]}
        For schema docs: {table_name, table: {...}, columns: [...], ...}
        """
        if doc.source_system == "confluence":
            return {
                "page_id": doc.source_document_id,
                "title": doc.title,
                "url": doc.source_uri,
                "space": doc.metadata.get("space_key", ""),
                "content": doc.full_text(),
                "items": doc.metadata.get("extracted_items", []),
                "metadata": {
                    "document_id": doc.document_id,
                    "processed_at": doc.processed_at.isoformat(),
                    "tags": doc.tags,
                },
            }
        elif doc.source_system == "athena":
            return {
                "table_name": doc.metadata.get("table_name", doc.title),
                "database": doc.metadata.get("database", ""),
                "table_comment": doc.metadata.get("table_comment", ""),
                "storage_format": doc.metadata.get("storage_format", ""),
                "s3_location": doc.metadata.get("s3_location", ""),
                "owner": doc.metadata.get("owner", ""),
                "row_count": doc.metadata.get("row_count"),
                "columns": doc.metadata.get("columns", []),
                "partition_keys": doc.metadata.get("partition_keys", []),
                "content": doc.full_text(),
                "metadata": {
                    "document_id": doc.document_id,
                    "processed_at": doc.processed_at.isoformat(),
                    "tags": doc.tags,
                },
            }
        else:
            return {
                "title": doc.title,
                "source_system": doc.source_system,
                "source_uri": doc.source_uri,
                "content": doc.full_text(),
                "metadata": {
                    "document_id": doc.document_id,
                    "processed_at": doc.processed_at.isoformat(),
                    "tags": doc.tags,
                    **doc.metadata,
                },
            }

    def _to_knowledge_format(self, doc: CanonicalDocument) -> dict[str, Any]:
        """Produce a flat, Qdrant-ready knowledge document.

        Each document becomes ONE embedding point with:
        - ``text``: the full content to embed (LLM-structured if available)
        - ``payload``: rich metadata for filtered retrieval
        - All LLM-enriched fields (summary, entities, salient_points, etc.)
          are promoted to top-level for easy access.
        """
        meta = doc.metadata

        # Build the embedding text — prefer LLM-structured overview + salient points
        structured = meta.get("structured_content", {})
        text_parts: list[str] = []

        # Title always first
        if doc.title:
            text_parts.append(f"# {doc.title}")

        # Summary from LLM enrichment
        summary = meta.get("summary", "")
        if summary:
            text_parts.append(summary)

        # Full extracted content
        full_text = doc.full_text()
        if full_text:
            text_parts.append(full_text)

        text = "\n\n".join(text_parts)

        result: dict[str, Any] = {
            # Identity
            "document_id": doc.document_id,
            "source_system": doc.source_system,
            "source_uri": doc.source_uri,
            "source_document_id": doc.source_document_id,
            "title": doc.title,

            # Embedding text (the content to vectorize)
            "text": text,

            # Classification
            "document_type": meta.get("document_type", "general"),
            "domains": doc.tags,
            "language": doc.provenance.quality.language_detected or "",

            # LLM-enriched knowledge (top-level for Qdrant payload filtering)
            "summary": summary,
            "key_entities": meta.get("key_entities", []),
            "abbreviations": meta.get("abbreviations", {}),

            # Quality
            "quality_score": doc.provenance.quality.extraction_confidence,
            "quality_dimensions": meta.get("quality_dimensions", {}),
            "document_signals": meta.get("document_signals", {}),

            # Structured knowledge sections (the LLM-restructured content)
            "structured_content": structured,

            # Tables preserved separately for structured retrieval
            "tables": [
                {
                    "headers": b.headers,
                    "rows": b.rows,
                    "caption": getattr(b, "caption", None),
                    "markdown": b.markdown,
                }
                for b in doc.content_blocks
                if hasattr(b, "headers")
            ],

            # Links for graph
            "links": [link.model_dump() for link in doc.links],

            # Source metadata
            "space_key": meta.get("space_key", ""),
            "processed_at": doc.processed_at.isoformat(),
        }

        return result


class ProgressTrackingWriter(BaseWriter):
    """Writer that tracks processed document IDs for resume capability.

    Wraps another writer and maintains a progress file to skip already-
    processed documents on re-runs.
    """

    name = "progress_tracking_writer"

    def __init__(
        self,
        inner_writer: BaseWriter,
        progress_file: str | Path,
        flush_interval: int = 25,
    ):
        self.inner = inner_writer
        self.progress_file = Path(progress_file)
        self.flush_interval = flush_interval
        self._done_ids: set[str] = self._load_progress()
        self._dirty = 0

    def write(self, doc: CanonicalDocument) -> str:
        if doc.document_id in self._done_ids:
            log.debug("Skipping already-processed document: %s", doc.document_id[:12])
            return ""

        result = self.inner.write(doc)
        self._done_ids.add(doc.document_id)
        self._dirty += 1

        if self._dirty >= self.flush_interval:
            self.flush()

        return result

    def flush(self) -> None:
        self.inner.flush()
        if self._dirty > 0:
            self._save_progress()
            self._dirty = 0

    def _load_progress(self) -> set[str]:
        if self.progress_file.exists():
            try:
                data = json.loads(self.progress_file.read_text())
                return set(data.get("processed_ids", []))
            except Exception:
                return set()
        return set()

    def _save_progress(self) -> None:
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "processed_ids": sorted(self._done_ids),
            "count": len(self._done_ids),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self.progress_file.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
