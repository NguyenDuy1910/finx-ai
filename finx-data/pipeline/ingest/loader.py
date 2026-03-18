"""Load knowledge JSON files from the preprocessed output directory."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

log = logging.getLogger("finx-data.ingest.loader")

# Files produced by the pipeline infrastructure — not knowledge documents
_SKIP_FILES = {".pipeline_progress.json"}


class KnowledgeLoader:
    """Yields knowledge document dicts from a directory of JSON files."""

    def __init__(self, knowledge_dir: str | Path) -> None:
        self.knowledge_dir = Path(knowledge_dir)

    def load_all(self) -> Iterator[dict]:
        """Yield each knowledge document as a plain dict.

        Skips infrastructure files and logs a warning on malformed JSON.
        """
        files = sorted(self.knowledge_dir.glob("*.json"))
        # Exclude pipeline infrastructure files
        files = [f for f in files if f.name not in _SKIP_FILES]

        log.info("Loading %d knowledge files from %s", len(files), self.knowledge_dir)

        for path in files:
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                doc["_source_path"] = str(path)
                yield doc
            except json.JSONDecodeError as exc:
                log.warning("Skipping malformed JSON file %s: %s", path.name, exc)
