"""Knowledge indexing package — public API.

Structure (new graph-based pipeline)
-------------------------------------
base.py               — abstract BaseSource (contract for all data sources)
pipeline.py           — IndexingPipeline (wires source → extractor → merger → store)
runner.py             — CLI entrypoint (typer)
sources/              — pluggable data source implementations
  schema_source.py    — finx-data/output/schema/*.json
  confluence_source.py— finx-data/output/confluence/*.json

Graph-level modules (in ``src.knowledge.graph``)
--------------------------------------------------
extractor.py          — LLM extraction engine (chunk → entities + edges)
merger.py             — graph merge engine (dedup before write)
prompts.py            — banking-specific extraction prompts

Structure (legacy Graphiti-based — still available)
----------------------------------------------------
utils/models.py       — shared dataclasses (EpisodePayload, PreparedItem, IngestionRequest, …)
utils/text.py         — pure text helpers (split_sections, slugify, utc_now)
utils/readers.py      — document readers (PDF, URL, Confluence)
utils/events.py       — LLM event helpers (infer_route, build_extraction_agent, …)

workflow.py           — IndexingWorkflow (generic orchestrator) + TextSource
document_ingestion.py — DocumentIngestionWorkflow + DocumentSource (PDF/URL/Confluence + LLM)
schema_metadata.py    — SchemaMetadataWorkflow + SchemaMetadataSource (Athena table schemas)
"""
from __future__ import annotations

# ── NEW: Graph-based pipeline ─────────────────────────────────────────────────
try:
    from src.knowledge.indexing.base import BaseSource, RawDocument
    from src.knowledge.graph.extractor import Extractor
    from src.knowledge.graph.merger import Merger
    from src.knowledge.indexing.pipeline import IndexingPipeline, IndexingStats
except ImportError:
    BaseSource = None  # type: ignore[assignment,misc]
    RawDocument = None  # type: ignore[assignment,misc]
    Extractor = None  # type: ignore[assignment,misc]
    Merger = None  # type: ignore[assignment,misc]
    IndexingPipeline = None  # type: ignore[assignment,misc]
    IndexingStats = None  # type: ignore[assignment,misc]

# ── LEGACY: Shared primitives ─────────────────────────────────────────────────
from src.knowledge.indexing.utils.models import (
    EpisodePayload,
    PreparedItem,
    IngestionInputType,
    IngestionRequest,
    SourceSection,
    PreparedEpisode,
    IngestionState,
)

# ── Source registry helpers ───────────────────────────────────────────────────
from src.knowledge.indexing.source import IndexingSource, get_source_class, registered_source_types

# ── Generic orchestrator + TextSource ────────────────────────────────────────
from src.knowledge.indexing.workflow import IndexingWorkflow, TextSource

# ── Feature workflows ─────────────────────────────────────────────────────────
from src.knowledge.indexing.schema_metadata import (
    SchemaMetadataWorkflow,
    SchemaMetadataSource,
    build_episode,
)
from src.knowledge.indexing.document_ingestion import (
    DocumentIngestionWorkflow,
    DocumentSource,
)

__all__ = [
    # NEW: Graph-based pipeline
    "BaseSource",
    "RawDocument",
    "Extractor",
    "Merger",
    "IndexingPipeline",
    "IndexingStats",
    # Legacy: Primitives
    "EpisodePayload",
    "PreparedItem",
    "IngestionInputType",
    "IngestionRequest",
    "SourceSection",
    "PreparedEpisode",
    "IngestionState",
    # Registry
    "IndexingSource",
    "get_source_class",
    "registered_source_types",
    # Generic orchestrator
    "IndexingWorkflow",
    # Sources
    "TextSource",
    "SchemaMetadataSource",
    "DocumentSource",
    # Feature workflows
    "SchemaMetadataWorkflow",
    "DocumentIngestionWorkflow",
    # Schema helper
    "build_episode",
]
