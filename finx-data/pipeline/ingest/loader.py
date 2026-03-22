"""Load canonical CanonicalDocument JSON files."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from pipeline.schemas.canonical import CanonicalDocument

log = logging.getLogger("finx-data.ingest.loader")

# Files produced by the pipeline infrastructure — not knowledge documents
_SKIP_FILES = {".pipeline_progress.json"}


class CanonicalLoader:
    """Yields CanonicalDocument objects from canonical JSON files."""

    def __init__(self, canonical_dir: str | Path) -> None:
        """Initialize loader.

        Args:
            canonical_dir: Directory containing canonical JSON files (from JSONWriter)
        """
        self.canonical_dir = Path(canonical_dir)

    def load_all(self) -> Iterator[CanonicalDocument]:
        """Yield each CanonicalDocument parsed from JSON.

        Skips infrastructure files and logs warnings on malformed JSON.

        Yields:
            CanonicalDocument instances
        """
        files = sorted(self.canonical_dir.glob("*.json"))
        # Exclude pipeline infrastructure files
        files = [f for f in files if f.name not in _SKIP_FILES]

        log.info("Loading %d canonical files from %s", len(files), self.canonical_dir)

        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                doc = CanonicalDocument.model_validate(data)
                yield doc
            except json.JSONDecodeError as exc:
                log.warning("Skipping malformed JSON file %s: %s", path.name, exc)
            except Exception as exc:
                log.warning("Skipping unparseable canonical document %s: %s", path.name, exc)
