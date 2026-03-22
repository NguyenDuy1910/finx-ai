"""ChunkDocument JSON writer — writes chunks as individual JSON files.

Produces chunk-level JSON files consumed by the Qdrant ingest stage.
Each CanonicalDocument is chunked by the ChunkerRouter, then each
ChunkDocument is serialized to a separate JSON file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pipeline.schemas.chunk import ChunkDocument
from .base import BaseWriter

log = logging.getLogger("finx-data.writer.chunk")


class ChunkWriter:
    """Write ChunkDocument objects as individual JSON files.

    Not a BaseWriter subclass because it operates on ChunkDocuments,
    not CanonicalDocuments. Used by the chunking stage of PipelineEngine.
    """

    def __init__(
        self,
        output_dir: str | Path,
        *,
        overwrite: bool = False,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.overwrite = overwrite
        self._written = 0

    def write_chunks(self, chunks: list[ChunkDocument]) -> list[str]:
        """Write a list of ChunkDocuments to disk.

        Returns list of written file paths.
        """
        paths: list[str] = []
        for chunk in chunks:
            path = self._write_one(chunk)
            if path:
                paths.append(path)
        return paths

    def _write_one(self, chunk: ChunkDocument) -> str | None:
        """Write a single ChunkDocument as JSON."""
        filename = f"{chunk.chunk_kind.value}_{chunk.chunk_position:03d}.json"

        # Group by page subfolder then chunks/ subdirectory
        page_name = self._safe_dirname(chunk)
        doc_dir = self.output_dir / page_name / "chunks"
        doc_dir.mkdir(parents=True, exist_ok=True)
        path = doc_dir / filename

        if path.exists() and not self.overwrite:
            log.debug("Skipping existing chunk file: %s", path)
            return None

        data = json.loads(chunk.model_dump_json())
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        self._written += 1
        return str(path)

    @property
    def total_written(self) -> int:
        return self._written

    def flush(self) -> None:
        """No-op for file writer."""
        pass

    @staticmethod
    def _safe_dirname(chunk: ChunkDocument) -> str:
        """Build a human-readable page subfolder name from chunk metadata."""
        ext_id = chunk.external_id or chunk.doc_id[:12]
        title = chunk.doc_title or ""
        safe_title = "".join(c if c.isalnum() or c in "-_." else "_" for c in title)[:80].rstrip("_")
        return f"{ext_id}_{safe_title}" if safe_title else str(ext_id)
