"""Local filesystem adapter.

Reads JSON, markdown, CSV/TSV, and PDF files from local directories.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from .base import BaseAdapter, RawDocument

log = logging.getLogger("finx-data.adapter.local")


class LocalFileAdapter(BaseAdapter):
    """Read structured and unstructured files from local directories."""

    source_system = "local"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        """Yield one RawDocument per file, auto-detecting format."""
        if not self.directory.exists():
            log.warning("Directory does not exist: %s", self.directory)
            return

        globs = kwargs.get("globs", ["*.json", "*.md", "*.csv", "*.tsv", "*.txt", "*.pdf"])
        for pattern in globs:
            for fpath in sorted(self.directory.glob(pattern)):
                if fpath.name.startswith("."):
                    continue
                try:
                    yield from self._read_file(fpath)
                except Exception as exc:
                    log.warning("Could not read %s: %s", fpath, exc)

    def _read_file(self, fpath: Path) -> Iterator[RawDocument]:
        suffix = fpath.suffix.lower()
        if suffix == ".json":
            yield from self._read_json(fpath)
        elif suffix in (".md", ".txt"):
            yield self._read_text(fpath)
        elif suffix in (".csv", ".tsv"):
            yield self._read_tabular(fpath)
        elif suffix == ".pdf":
            yield self._read_binary(fpath, "application/pdf")
        else:
            yield self._read_text(fpath)

    def _read_json(self, fpath: Path) -> Iterator[RawDocument]:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            yield RawDocument(
                source_system=self.source_system,
                source_uri=str(fpath.resolve()),
                source_id=fpath.stem,
                title=data.get("title", data.get("name", fpath.stem)),
                raw_content=json.dumps(data, indent=2, ensure_ascii=False),
                metadata={"file_name": fpath.name, "format": "json"},
                mime_type="application/json",
            )
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    yield RawDocument(
                        source_system=self.source_system,
                        source_uri=f"{fpath.resolve()}#{i}",
                        source_id=f"{fpath.stem}_{i}",
                        title=item.get("title", item.get("name", f"{fpath.stem}_{i}")),
                        raw_content=json.dumps(item, indent=2, ensure_ascii=False),
                        metadata={"file_name": fpath.name, "index": i, "format": "json"},
                        mime_type="application/json",
                    )

    def _read_text(self, fpath: Path) -> RawDocument:
        content = fpath.read_text(encoding="utf-8", errors="replace").strip()
        return RawDocument(
            source_system=self.source_system,
            source_uri=str(fpath.resolve()),
            source_id=fpath.stem,
            title=fpath.stem,
            raw_content=content,
            metadata={"file_name": fpath.name, "format": fpath.suffix.lstrip(".")},
            mime_type="text/markdown" if fpath.suffix == ".md" else "text/plain",
        )

    def _read_tabular(self, fpath: Path) -> RawDocument:
        import csv

        delimiter = "\t" if fpath.suffix == ".tsv" else ","
        with fpath.open(newline="", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            rows = list(reader)

        if not rows:
            return RawDocument(
                source_system=self.source_system,
                source_uri=str(fpath.resolve()),
                source_id=fpath.stem,
                title=fpath.stem,
                raw_content="",
                metadata={"file_name": fpath.name, "format": "csv", "row_count": 0},
            )

        headers = list(rows[0].keys())
        lines = [f"Source: {fpath.name}", f"Columns: {', '.join(headers)}", ""]
        for row in rows:
            line_parts = [f"{h}: {row.get(h, '')}" for h in headers]
            lines.append(" | ".join(line_parts))

        return RawDocument(
            source_system=self.source_system,
            source_uri=str(fpath.resolve()),
            source_id=fpath.stem,
            title=fpath.stem,
            raw_content="\n".join(lines),
            metadata={
                "file_name": fpath.name,
                "format": fpath.suffix.lstrip("."),
                "row_count": len(rows),
                "columns": headers,
            },
            mime_type="text/csv",
        )

    def _read_binary(self, fpath: Path, mime: str) -> RawDocument:
        return RawDocument(
            source_system=self.source_system,
            source_uri=str(fpath.resolve()),
            source_id=fpath.stem,
            title=fpath.stem,
            binary_content=fpath.read_bytes(),
            metadata={"file_name": fpath.name, "format": fpath.suffix.lstrip(".")},
            mime_type=mime,
        )
