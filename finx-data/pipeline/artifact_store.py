"""Raw Artifact Store — persist fetched content before processing.

This layer sits between Source Adapters and the parsing pipeline.
It saves every raw document to local disk (or object storage) with a
manifest that tracks what was fetched, when, and its content hash.

Purpose
-------
- Decouple fetching from processing (can re-process without re-fetching)
- Enable incremental fetching (skip already-downloaded artifacts)
- Full audit trail of raw inputs
- Support offline / air-gapped processing
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.adapters.base import RawDocument

log = logging.getLogger("finx-data.artifact_store")


class ArtifactManifest:
    """Tracks all raw artifacts that have been stored.

    The manifest is a JSON file mapping content_hash → artifact metadata.
    It enables:
    - Deduplication (same content from different fetches)
    - Incremental ingestion (skip already-stored artifacts)
    - Re-processing from raw layer without re-fetching
    """

    def __init__(self, manifest_path: Path):
        self.path = manifest_path
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._entries = data.get("artifacts", {})
            except Exception as exc:
                log.warning("Could not load manifest %s: %s", self.path, exc)
                self._entries = {}

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "artifact_count": len(self._entries),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "artifacts": self._entries,
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        self._dirty = False

    def has(self, content_hash: str) -> bool:
        return content_hash in self._entries

    def get(self, content_hash: str) -> dict[str, Any] | None:
        return self._entries.get(content_hash)

    def add(self, content_hash: str, entry: dict[str, Any]) -> None:
        self._entries[content_hash] = entry
        self._dirty = True

    @property
    def count(self) -> int:
        return len(self._entries)

    def all_entries(self) -> list[dict[str, Any]]:
        return list(self._entries.values())


class RawArtifactStore:
    """Persist raw documents to disk with a tracking manifest.

    Directory layout::

        raw_artifacts/
        ├── _manifest.json          # tracks all stored artifacts
        ├── confluence/
        │   ├── page_123.content    # raw text content
        │   ├── page_123.meta.json  # metadata envelope
        │   └── page_123.html       # raw HTML (if present)
        ├── athena/
        │   ├── db__users.content
        │   └── db__users.meta.json
        └── s3/
            ├── report.pdf          # binary artifact
            └── report.meta.json
    """

    def __init__(self, store_dir: str | Path):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ArtifactManifest(self.store_dir / "_manifest.json")

    def store(self, raw: RawDocument, *, skip_existing: bool = True) -> Path:
        """Persist a RawDocument to disk. Returns path to the meta file.

        If ``skip_existing`` is True and the artifact's content hash is
        already in the manifest, the write is skipped.
        """
        content_hash = raw.content_hash
        if skip_existing and self.manifest.has(content_hash):
            log.debug("Artifact already stored: %s", raw.source_uri)
            entry = self.manifest.get(content_hash)
            return Path(entry["meta_path"]) if entry else self.store_dir

        # Build artifact directory: raw_artifacts/<source_system>/
        source_dir = self.store_dir / self._safe(raw.source_system)
        source_dir.mkdir(parents=True, exist_ok=True)

        # Safe file stem
        stem = self._safe(raw.source_id or raw.title or content_hash[:16])

        # Write text content (use .md for easy preview in editors)
        content_path = source_dir / f"{stem}.md"
        if raw.raw_content:
            content_path.write_text(raw.raw_content, encoding="utf-8")

        # Write HTML if present
        html_path: str | None = None
        if raw.raw_html:
            hp = source_dir / f"{stem}.html"
            hp.write_text(raw.raw_html, encoding="utf-8")
            html_path = str(hp)

        # Write binary if present
        binary_path: str | None = None
        if raw.binary_content:
            ext = self._ext_for_mime(raw.mime_type)
            bp = source_dir / f"{stem}{ext}"
            bp.write_bytes(raw.binary_content)
            binary_path = str(bp)

        # Write metadata envelope
        meta = {
            "source_system": raw.source_system,
            "source_uri": raw.source_uri,
            "source_id": raw.source_id,
            "title": raw.title,
            "mime_type": raw.mime_type,
            "content_hash": content_hash,
            "content_path": str(content_path) if raw.raw_content else None,
            "html_path": html_path,
            "binary_path": binary_path,
            "fetched_at": raw.fetched_at.isoformat(),
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "metadata": raw.metadata,
        }
        meta_path = source_dir / f"{stem}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))

        # Update manifest
        self.manifest.add(content_hash, {
            "source_system": raw.source_system,
            "source_uri": raw.source_uri,
            "source_id": raw.source_id,
            "title": raw.title,
            "mime_type": raw.mime_type,
            "content_hash": content_hash,
            "meta_path": str(meta_path),
            "stored_at": meta["stored_at"],
        })

        log.debug("Stored artifact: %s → %s", raw.source_uri, meta_path)
        return meta_path

    def flush(self) -> None:
        """Write manifest to disk."""
        self.manifest.save()

    def load_raw_document(self, meta_path: str | Path) -> RawDocument:
        """Reconstruct a RawDocument from a stored artifact."""
        meta_path = Path(meta_path)
        meta = json.loads(meta_path.read_text())

        raw_content = ""
        if meta.get("content_path"):
            cp = Path(meta["content_path"])
            if cp.exists():
                raw_content = cp.read_text(encoding="utf-8", errors="replace")

        raw_html = ""
        if meta.get("html_path"):
            hp = Path(meta["html_path"])
            if hp.exists():
                raw_html = hp.read_text(encoding="utf-8", errors="replace")

        binary_content = None
        if meta.get("binary_path"):
            bp = Path(meta["binary_path"])
            if bp.exists():
                binary_content = bp.read_bytes()

        return RawDocument(
            source_system=meta["source_system"],
            source_uri=meta["source_uri"],
            source_id=meta.get("source_id", ""),
            title=meta.get("title", ""),
            raw_content=raw_content,
            raw_html=raw_html,
            binary_content=binary_content,
            mime_type=meta.get("mime_type", ""),
            metadata=meta.get("metadata", {}),
        )

    def iter_stored(self) -> list[RawDocument]:
        """Iterate all stored artifacts, yielding RawDocuments."""
        docs: list[RawDocument] = []
        for entry in self.manifest.all_entries():
            meta_path = entry.get("meta_path", "")
            if meta_path and Path(meta_path).exists():
                try:
                    docs.append(self.load_raw_document(meta_path))
                except Exception as exc:
                    log.warning("Failed to load artifact %s: %s", meta_path, exc)
        return docs

    @staticmethod
    def _safe(name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)

    @staticmethod
    def _ext_for_mime(mime: str) -> str:
        _map = {
            "application/pdf": ".pdf",
            "text/html": ".html",
            "text/markdown": ".md",
            "text/plain": ".txt",
            "text/csv": ".csv",
            "application/json": ".json",
            "image/png": ".png",
            "image/jpeg": ".jpg",
        }
        return _map.get(mime, ".bin")
