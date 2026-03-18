from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from .schemas import ConfluenceFile, SchemaFile

logger = logging.getLogger(__name__)

ConfluenceKind = Literal["structured", "unstructured"]


def discover_schema_files(base_dir: Path, schema_subdir: str = "schema") -> list[Path]:
    schema_dir = base_dir / schema_subdir
    if not schema_dir.exists():
        logger.warning("Schema directory not found: %s", schema_dir)
        return []
    files = sorted(p for p in schema_dir.glob("*.json") if not p.name.startswith("_"))
    logger.info("Discovered %d schema files in %s", len(files), schema_dir)
    return files


def discover_confluence_files(base_dir: Path) -> list[Path]:
    conf_dir = base_dir / "confluence"
    if not conf_dir.exists():
        logger.warning("Confluence directory not found: %s", conf_dir)
        return []
    files = sorted(p for p in conf_dir.glob("*.json") if not p.name.startswith("."))
    logger.info("Discovered %d confluence files", len(files))
    return files


def load_schema_file(path: Path) -> SchemaFile | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        obj = SchemaFile.model_validate(raw)
        obj.file_path = str(path)
        return obj
    except Exception as e:
        logger.error("Failed to load schema file %s: %s", path.name, e)
        return None


def load_confluence_file(path: Path) -> ConfluenceFile | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        obj = ConfluenceFile.model_validate(raw)
        obj.file_path = str(path)
        return obj
    except Exception as e:
        logger.error("Failed to load confluence file %s: %s", path.name, e)
        return None


def classify_confluence_file(cf: ConfluenceFile) -> ConfluenceKind:
    return "structured" if cf.is_structured else "unstructured"


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_bootstrap_state(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_bootstrap_state(state_path: Path, state: dict[str, str]) -> None:
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def is_already_processed(path: Path, state: dict[str, str]) -> bool:
    key = str(path)
    return key in state and state[key] == _file_hash(path)


def mark_processed(path: Path, state: dict[str, str]) -> None:
    state[str(path)] = _file_hash(path)
