"""Chunk builder — converts finx-data JSON records into rich text Chunks for LLM extraction.

**LLM-first approach**: ALL data (schema, confluence) is converted into
comprehensive text Chunks and sent through the LLM Extractor → Merger →
GraphStore pipeline.  The LLM decides what entities and relationships are
meaningful — no hardcoded deterministic node/edge creation.

The builder's job is to produce high-quality text representations that give
the LLM enough context to extract a rich knowledge graph.
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.knowledge.graph.models import Chunk

from .group_id_strategy import normalize_domain
from .schemas import ColumnMeta, ConfluenceFile, ConfluenceItem, SchemaFile

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  Schema → Chunks
# ═══════════════════════════════════════════════════════════════════════════════

def build_schema_chunks(
    sf: SchemaFile,
    max_top_columns: int = 10,
) -> list[Chunk]:
    """Convert a schema file into rich text Chunks for LLM extraction.

    Produces ONE comprehensive chunk per schema file that includes ALL metadata:
    table info, columns (ALL columns with full detail), grains, relationships,
    dataset, semantic model.  The LLM then decides what entities/relationships
    to create from this rich context.
    """
    if sf.dataset:
        return _build_dataset_chunk(sf)
    if sf.semantic_model:
        return _build_semantic_model_chunk(sf)
    if sf.table:
        return _build_table_chunk(sf, max_top_columns)
    return []


def _build_dataset_chunk(sf: SchemaFile) -> list[Chunk]:
    """Build chunk for a Dataset-type schema file."""
    d = sf.dataset
    if not d:
        return []

    parts: list[str] = []
    parts.append(f"=== Dataset: {d.name} ===")
    if d.database:
        parts.append(f"Database: {d.database}")
    if d.domain:
        parts.append(f"Domain: {d.domain}")
    if d.description:
        parts.append(f"Description: {d.description}")
    if d.owner:
        parts.append(f"Owner: {d.owner}")
    if d.synonyms:
        parts.append(f"Synonyms: {', '.join(d.synonyms)}")
    if d.tags:
        parts.append(f"Tags: {', '.join(d.tags)}")

    content = "\n".join(parts)
    if len(content) < 50:
        return []

    return [Chunk(
        id=Chunk.make_id(content),
        content=content,
        source_id="schema",
        file_path=sf.file_path,
        doc_id=f"schema:{Path(sf.file_path).stem}",
    )]


def _build_semantic_model_chunk(sf: SchemaFile) -> list[Chunk]:
    """Build chunk for a SemanticModel-type schema file."""
    sm = sf.semantic_model
    if not sm:
        return []

    parts: list[str] = []
    parts.append(f"=== Semantic Model: {sm.name} ===")
    if sm.domain:
        parts.append(f"Domain: {sm.domain}")
    if sm.description:
        parts.append(f"Description: {sm.description}")
    if sm.metrics:
        parts.append(f"Metrics: {', '.join(sm.metrics)}")
    if sm.dimensions:
        parts.append(f"Dimensions: {', '.join(sm.dimensions)}")
    if sm.tables:
        parts.append(f"Source tables: {', '.join(sm.tables)}")
    if sm.synonyms:
        parts.append(f"Synonyms: {', '.join(sm.synonyms)}")
    if sm.tags:
        parts.append(f"Tags: {', '.join(sm.tags)}")

    content = "\n".join(parts)
    if len(content) < 50:
        return []

    return [Chunk(
        id=Chunk.make_id(content),
        content=content,
        source_id="schema",
        file_path=sf.file_path,
        doc_id=f"schema:{Path(sf.file_path).stem}",
    )]


def _build_table_chunk(sf: SchemaFile, max_top_columns: int = 10) -> list[Chunk]:
    """Build a comprehensive chunk for a Table-type schema file.

    Includes ALL table metadata + ALL columns with full detail so the LLM
    has maximum context for extracting meaningful entities and relationships.
    """
    t = sf.table
    if not t:
        return []

    parts: list[str] = []
    parts.append(f"=== Table: {t.table_name} ===")

    if t.database:
        parts.append(f"Database: {t.database}")
    if t.dataset:
        parts.append(f"Dataset: {t.dataset}")
    if t.domain:
        parts.append(f"Domain: {t.domain}")
    if t.description:
        parts.append(f"Description: {t.description}")
    if t.ai_description and t.ai_description != t.description:
        parts.append(f"AI analysis: {t.ai_description}")
    if t.synonyms:
        parts.append(f"Synonyms: {', '.join(t.synonyms)}")
    if t.tags:
        parts.append(f"Tags: {', '.join(t.tags)}")
    if t.partition_keys:
        parts.append(f"Partition keys: {', '.join(t.partition_keys)}")
    if t.storage_format:
        parts.append(f"Storage: {t.storage_format}")
    if t.certification_status:
        parts.append(f"Certification: {t.certification_status}")

    # Table-level relationships from metadata
    if t.relationships:
        parts.append("Table relationships:")
        for rel in t.relationships:
            tgt = rel.get("target_name", "")
            etype = rel.get("edge_type", "")
            desc = rel.get("description", "")
            if tgt:
                parts.append(f"  - {etype}: {t.table_name} → {tgt}" + (f" ({desc})" if desc else ""))

    # ALL columns with full detail
    all_cols = sf.columns or []
    if all_cols:
        parts.append(f"\nColumns ({len(all_cols)} total):")
        for col in all_cols:
            col_line = _format_column(col)
            parts.append(col_line)

    # Grains
    for g in (sf.grains or []):
        cols = ", ".join(g.grain_columns) if g.grain_columns else ""
        gran = g.time_granularity or ""
        desc = f" — {g.description}" if g.description else ""
        parts.append(f"Grain: {g.name or 'unnamed'} ({gran}) by [{cols}]{desc}")

    content = "\n".join(parts)

    # Always create a chunk if there's a table name — let the LLM judge value
    if len(content) < 50:
        return []

    return [Chunk(
        id=Chunk.make_id(content),
        content=content,
        source_id="schema",
        file_path=sf.file_path,
        doc_id=f"schema:{Path(sf.file_path).stem}",
    )]


def _format_column(col: ColumnMeta) -> str:
    """Format a column into a rich single-line description for the LLM."""
    flags: list[str] = []
    if col.is_primary_key:
        flags.append("PK")
    if col.is_partition_key:
        flags.append("PARTITION")
    if col.is_nullable:
        flags.append("nullable")

    flag_str = f" [{', '.join(flags)}]" if flags else ""
    dtype_str = f" ({col.data_type})" if col.data_type else ""
    desc_str = f": {col.description}" if col.description else ""
    synonym_str = f" (also: {', '.join(col.synonyms)})" if col.synonyms else ""

    # Include column-level relationships if present (skip redundant STORED_IN)
    rel_strs: list[str] = []
    for rel in col.relationships:
        tgt = rel.get("target_name", "")
        etype = rel.get("edge_type", "")
        if tgt and etype != "STORED_IN":
            rel_strs.append(f"{etype}→{tgt}")
    rel_part = f" [rels: {'; '.join(rel_strs)}]" if rel_strs else ""

    return f"  - {col.column_name}{dtype_str}{flag_str}{desc_str}{synonym_str}{rel_part}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Confluence → Chunks
# ═══════════════════════════════════════════════════════════════════════════════

def build_confluence_chunks(
    cf: ConfluenceFile,
) -> list[Chunk]:
    """Convert a Confluence file into text Chunks for LLM extraction.

    Each item with sufficient content becomes its own chunk.
    Items are rendered as rich text with all available metadata.
    """
    chunks: list[Chunk] = []
    doc_id = f"confluence:{cf.page_id or Path(cf.file_path).stem}"

    for item in cf.items:
        content = _format_confluence_item(item, cf)
        if len(content) < 50:
            continue

        chunks.append(Chunk(
            id=Chunk.make_id(content),
            content=content,
            source_id="confluence",
            file_path=cf.file_path,
            doc_id=doc_id,
        ))

    return chunks


def _format_confluence_item(item: ConfluenceItem, cf: ConfluenceFile) -> str:
    """Format a single Confluence item into rich text for the LLM."""
    parts: list[str] = []

    name = item.display_name
    if name:
        parts.append(f"=== {item.entity_type}: {name} ===")
    else:
        parts.append(f"=== {item.entity_type} ===")

    if cf.space:
        parts.append(f"Space: {cf.space}")
    if item.domain:
        parts.append(f"Domain: {item.domain}")
    if item.definition:
        parts.append(f"Definition: {item.definition}")
    if item.description and item.description != item.definition:
        parts.append(f"Description: {item.description}")
    if item.synonyms:
        parts.append(f"Synonyms: {', '.join(item.synonyms)}")
    if item.tags:
        parts.append(f"Tags: {', '.join(item.tags)}")
    if item.notes:
        parts.append(f"Notes: {item.notes}")

    # Authority/ownership
    if item.authority_level:
        parts.append(f"Authority level: {item.authority_level}")
    if item.owner_team:
        parts.append(f"Owner team: {item.owner_team}")
    if item.role_name:
        parts.append(f"Role: {item.role_name}")
    if item.permissions:
        parts.append(f"Permissions: {', '.join(item.permissions)}")

    # Provenance
    if item.source_document:
        parts.append(f"Source document: {item.source_document}")
    if item.source_url:
        parts.append(f"Source URL: {item.source_url}")

    # Item-level relationships
    if item.relationships:
        parts.append("Relationships:")
        for rel in item.relationships:
            tgt = rel.get("target_name", "")
            etype = rel.get("edge_type", "")
            desc = rel.get("description", "")
            if tgt:
                parts.append(f"  - {etype}: {name} → {tgt}" + (f" ({desc})" if desc else ""))

    return "\n".join(parts)
