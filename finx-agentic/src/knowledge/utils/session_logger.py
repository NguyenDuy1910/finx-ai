"""
Session-based file logger for search pipeline debugging.

Each call to ``search_schema`` creates a separate log file under
``scripts/log_process/`` with a timestamped filename so every
request can be inspected independently.

Moved from ``src.knowledge.session_logger`` into the ``utils`` package.
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Resolve project root → scripts/log_process
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/knowledge/utils → finx-agentic
LOG_DIR = _PROJECT_ROOT / "scripts" / "log_process"


class SessionFileLogger:
    """Writes structured logs for a single search session to a dedicated file."""

    def __init__(self, filepath: Path, query: str, session_id: str):
        self._filepath = filepath
        self._session_id = session_id
        self._query = query
        self._lines: List[str] = []
        self._t0 = time.time()

        self._lines.append("=" * 80)
        self._lines.append(f"SESSION  : {session_id}")
        self._lines.append(f"QUERY    : {query}")
        self._lines.append(f"STARTED  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")
        self._lines.append("=" * 80)
        self._lines.append("")

    # ── public API ────────────────────────────────────────────────────

    def log(self, step: str, message: str, data: Any = None) -> None:
        elapsed = (time.time() - self._t0) * 1000
        line = f"[+{elapsed:7.0f}ms] [{step}] {message}"
        self._lines.append(line)
        if data is not None:
            formatted = self._format_data(data)
            for sub in formatted.split("\n"):
                self._lines.append(f"           {sub}")
            self._lines.append("")

    def log_separator(self, label: str = "") -> None:
        if label:
            self._lines.append(f"── {label} {'─' * max(0, 70 - len(label))}")
        else:
            self._lines.append("─" * 76)

    def log_summary(self, metadata: Dict[str, Any]) -> None:
        elapsed_ms = round((time.time() - self._t0) * 1000)
        self._lines.append("")
        self._lines.append("=" * 80)
        self._lines.append(f"FINISHED : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")
        self._lines.append(f"TOTAL    : {elapsed_ms}ms")
        self._lines.append("-" * 80)
        for k, v in metadata.items():
            self._lines.append(f"  {k}: {v}")
        self._lines.append("=" * 80)

    def close(self) -> None:
        try:
            self._filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self._lines) + "\n")
            logger.debug("Session log written → %s", self._filepath)
        except Exception as exc:
            logger.warning("Failed to write session log %s: %s", self._filepath, exc)

    # ── factory ───────────────────────────────────────────────────────

    @classmethod
    def create(cls, query: str, log_dir: Optional[Path] = None) -> "SessionFileLogger":
        target_dir = log_dir or LOG_DIR
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        slug = cls._slugify(query)[:60]
        session_id = f"{timestamp}_{slug}"
        filename = f"{session_id}.log"
        filepath = target_dir / filename
        return cls(filepath=filepath, query=query, session_id=session_id)

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "_", text)
        return text.strip("_") or "unknown"

    @staticmethod
    def _format_data(data: Any) -> str:
        if isinstance(data, (dict, list)):
            try:
                return json.dumps(data, ensure_ascii=False, indent=2, default=str)
            except (TypeError, ValueError):
                return str(data)
        return str(data)
