"""JSON file writer — writes canonical documents to disk as full CanonicalDocument JSON."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.schemas.canonical import CanonicalDocument
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
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.format = format
        self.overwrite = overwrite

    def write(self, doc: CanonicalDocument) -> str:
        page_dir = self.output_dir / self._safe_dirname(doc)
        page_dir.mkdir(parents=True, exist_ok=True)

        safe_name = self._safe_filename(doc)
        path = page_dir / f"{safe_name}.json"

        if path.exists() and not self.overwrite:
            log.debug("Skipping existing file: %s", path)
            return str(path)

        data = json.loads(doc.model_dump_json())

        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        log.debug("Wrote %s", path)
        return str(path)

    def _safe_dirname(self, doc: CanonicalDocument) -> str:
        """Generate a safe directory name per page/document.

        Uses the source_document_id (e.g. Confluence page_id) as the
        subfolder name, with the title appended for readability.
        Attachments and comments go under their parent's folder.
        """
        sct = (doc.source_content_type or "").lower()
        if sct in ("comment", "attachment") and doc.parent_document_id:
            # Use parent page's document_id as folder
            parent_id = doc.metadata.get("parent_content_id", "") or doc.parent_document_id[:12]
            parent_title = doc.metadata.get("parent_title", "")
            safe_parent = self._sanitize(parent_title or parent_id)
            return f"{parent_id}_{safe_parent}" if parent_title else str(parent_id)

        doc_id = doc.source_document_id or doc.document_id[:12]
        title = doc.title or ""
        safe_title = self._sanitize(title)
        return f"{doc_id}_{safe_title}" if safe_title else str(doc_id)

    def _safe_filename(self, doc: CanonicalDocument) -> str:
        """Generate a safe, deterministic filename."""
        sct = (doc.source_content_type or "").lower()
        if sct == "comment":
            comment_id = doc.source_document_id or doc.document_id[:12]
            return f"comment_{self._sanitize(comment_id)}"
        if sct == "attachment":
            att_name = doc.metadata.get("filename", "") or doc.title or doc.document_id[:12]
            return f"attachment_{self._sanitize(att_name)}"
        # Main page/document
        return "canonical"

    @staticmethod
    def _sanitize(name: str) -> str:
        """Sanitize a string for use as a directory/file name."""
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        return safe[:80].rstrip("_")

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

    @property
    def processed_ids(self) -> set[str]:
        """Set of document_ids that have already been processed."""
        return self._done_ids

    def is_done(self, document_id: str) -> bool:
        """Check whether a document_id was already processed."""
        return document_id in self._done_ids

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
