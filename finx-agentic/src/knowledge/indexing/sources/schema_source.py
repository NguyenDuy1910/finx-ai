"""Schema JSON data source — reads finx-data/output/schema/*.json.

Structured data (table name, columns, dataset) → deterministic upserts (no LLM).
AI descriptions and semantic content → LLM extraction.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from scripts.bootstrap.schemas import SchemaFile, ColumnMeta
from src.knowledge.graph.models import Chunk, NodeData, NodeLabel, EdgeType

from ..base import BaseSource, RawDocument

logger = logging.getLogger(__name__)


class SchemaSource(BaseSource):
    """``BaseSource`` implementation for ``finx-data/output/schema/*.json``."""

    def __init__(self, data_dir: Path, *, domain_filter: str | None = None) -> None:
        self._data_dir = data_dir
        self._domain_filter = domain_filter

    @property
    def source_id(self) -> str:
        return "schema"

    def discover(self) -> Iterator[RawDocument]:
        schema_dir = self._data_dir / "schema"
        if not schema_dir.exists():
            logger.warning("Schema directory not found: %s", schema_dir)
            return

        for path in sorted(schema_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                raw["file_path"] = str(path)
                sf = SchemaFile.model_validate(raw)

                # Optional domain filter
                if self._domain_filter and sf.effective_domain != self._domain_filter.lower():
                    continue

                yield RawDocument(
                    doc_id=path.stem,
                    content=sf,
                    file_path=str(path),
                    metadata={"domain": sf.effective_domain},
                )
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", path.name, exc)

    def to_chunks(self, doc: RawDocument) -> list[Chunk]:
        """Serialise the schema file into a text chunk for LLM extraction.

        Returns 1 chunk per document with AI description + relationship context.
        Pure structural data (table name, columns) is handled by ``deterministic_upserts``.
        """
        sf: SchemaFile = doc.content
        parts: list[str] = []

        if sf.table and sf.table.table_name:
            t = sf.table
            parts.append(f"Table: {t.table_name}")
            if t.database:
                parts.append(f"Database: {t.database}")
            if t.dataset:
                parts.append(f"Dataset: {t.dataset}")
            if t.domain:
                parts.append(f"Domain: {t.domain}")
            if t.description:
                parts.append(f"Description: {t.description}")
            if t.ai_description and t.ai_description != t.description:
                parts.append(f"AI Description: {t.ai_description}")
            if t.synonyms:
                parts.append(f"Synonyms: {', '.join(t.synonyms)}")
            if t.relationships:
                for rel in t.relationships:
                    parts.append(
                        f"Relationship: {rel.get('edge_type', '')} → "
                        f"{rel.get('target_type', '')}: {rel.get('target_name', '')}"
                    )

            # Include top columns for context
            for col in sf.top_columns(max_n=5):
                col_line = f"Column: {col.column_name} ({col.data_type})"
                if col.is_primary_key:
                    col_line += " [PK]"
                if col.description:
                    col_line += f" — {col.description}"
                parts.append(col_line)

        elif sf.dataset:
            d = sf.dataset
            parts.append(f"Dataset: {d.name}")
            if d.database:
                parts.append(f"Database: {d.database}")
            if d.description:
                parts.append(f"Description: {d.description}")
            if d.owner:
                parts.append(f"Owner: {d.owner}")

        elif sf.semantic_model:
            sm = sf.semantic_model
            parts.append(f"SemanticModel: {sm.name}")
            if sm.description:
                parts.append(f"Description: {sm.description}")

        if not parts:
            return []

        content = "\n".join(parts)
        return [
            Chunk(
                id=Chunk.make_id(content),
                content=content,
                source_id=self.source_id,
                file_path=doc.file_path,
                doc_id=doc.doc_id,
            )
        ]

    def deterministic_upserts(self, doc: RawDocument) -> list[NodeData]:
        """Upsert Table, Dataset, Column nodes without LLM — cost = $0."""
        sf: SchemaFile = doc.content
        nodes: list[NodeData] = []

        # Table node
        if sf.table and sf.table.table_name:
            t = sf.table
            nodes.append(NodeData(
                name=t.table_name.upper().strip(),
                label=NodeLabel.TABLE.value,
                description=t.description or t.ai_description or "",
                domain=t.domain or "",
                synonyms=t.synonyms or [],
                tags=t.tags or [],
                source_ids=[doc.doc_id],
                file_path=doc.file_path,
                extra={
                    "database": t.database,
                    "dataset": t.dataset,
                    "partition_keys": ",".join(t.partition_keys) if t.partition_keys else "",
                },
            ))

            # Column nodes
            for col in sf.columns:
                nodes.append(NodeData(
                    name=f"{t.table_name}.{col.column_name}".upper().strip(),
                    label=NodeLabel.COLUMN.value,
                    description=col.description or "",
                    synonyms=col.synonyms or [],
                    source_ids=[doc.doc_id],
                    file_path=doc.file_path,
                    extra={
                        "table_name": t.table_name,
                        "data_type": col.data_type,
                        "is_pk": str(col.is_primary_key),
                        "is_nullable": str(col.is_nullable),
                    },
                ))

        # Dataset node
        if sf.dataset:
            d = sf.dataset
            nodes.append(NodeData(
                name=(d.name or "").upper().strip(),
                label=NodeLabel.DATASET.value,
                description=d.description or "",
                domain=d.domain or "",
                tags=d.tags or [],
                synonyms=d.synonyms or [],
                source_ids=[doc.doc_id],
                file_path=doc.file_path,
                extra={"database": d.database, "owner": d.owner},
            ))

        return [n for n in nodes if n.name]  # filter blanks
