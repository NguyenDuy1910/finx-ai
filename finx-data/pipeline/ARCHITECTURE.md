# Pipeline Architecture

## Overview

The `pipeline/` package implements a modular, enterprise-grade preprocessing pipeline that transforms raw enterprise content into a canonical normalized format. It sits between external data sources and the downstream knowledge graph & vector store indexing systems.

```
┌─────────────────────────────────────────────────────────────────────┐
│                      finx-data Pipeline                             │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ Adapters │───>│Extractors│───>│Normalizer│───>│ Writers  │      │
│  │          │    │(Stage 1) │    │(Stage 2) │    │          │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│                                                                     │
│  Confluence       MinerU PDF      Rule-based      Canonical JSON    │
│  Athena/Glue      HTML parser     LLM enrichment  Legacy JSON       │
│  S3 objects       Markdown        Domain tagging   Progress track    │
│  Local files      Schema parser   Abbreviations                     │
└─────────────────────────────────────────────────────────────────────┘
         ↓                                              ↓
    External Sources                            output/pipeline/
                                                      ↓
                                          ┌──────────────────────┐
                                          │  finx-agentic        │
                                          │  Bootstrap indexing   │
                                          │  → FalkorDB graph     │
                                          │  → Vector embeddings  │
                                          └──────────────────────┘
```

## Package Structure

```
pipeline/
├── __init__.py              # Package metadata
├── cli.py                   # CLI entry point
├── engine.py                # Pipeline orchestrator
├── errors.py                # Error types & failure tracking
├── schemas/
│   ├── blocks.py            # Content block types (text, table, image, code, ...)
│   ├── canonical.py         # CanonicalDocument — the unified output schema
│   └── provenance.py        # Processing lineage & quality signals
├── adapters/
│   ├── base.py              # BaseAdapter + RawDocument
│   ├── confluence.py        # Confluence space/page adapter
│   ├── athena.py            # Athena/Glue schema metadata adapter
│   ├── s3.py                # S3 object adapter
│   └── local.py             # Local filesystem adapter
├── extractors/
│   ├── base.py              # BaseExtractor interface
│   ├── html.py              # HTML, Markdown, Schema extractors
│   └── mineru.py            # MinerU PDF extraction integration
├── normalizers/
│   ├── base.py              # BaseNormalizer interface
│   └── llm.py               # LLM + rule-based normalizers
└── writers/
    ├── base.py              # BaseWriter interface
    └── json_writer.py       # JSON writer + progress tracking
```

## Canonical Document Schema

The `CanonicalDocument` is the core data contract. Every stage operates on this type.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `document_id` | `str` | Deterministic SHA-256 hash of `(source_system, source_uri)` |
| `source_system` | `str` | Origin: `confluence`, `athena`, `s3`, `local` |
| `source_uri` | `str` | Unique locator within the source system |
| `source_document_id` | `str` | Native ID (page_id, table name) |
| `title` | `str` | Document title |
| `content_type` | `str` | `document`, `schema`, `api_spec`, `faq` |
| `section_hierarchy` | `list[SectionNode]` | Document outline tree |
| `content_blocks` | `list[ContentBlock]` | Ordered typed blocks |
| `links` | `list[LinkRef]` | Extracted hyperlinks |
| `metadata` | `dict` | Adapter-specific metadata |
| `tags` | `list[str]` | Domain/topic tags |
| `processed_at` | `datetime` | Processing timestamp |
| `provenance` | `Provenance` | Full audit trail |

### Content Block Types

- **TextBlock** — paragraphs, body text
- **HeadingBlock** — section headings (level 1-6)
- **TableBlock** — structured tables (headers + rows + markdown)
- **ImageBlock** — image references with descriptions
- **CodeBlock** — code/SQL snippets with language
- **ListBlock** — ordered/unordered lists

### Provenance

Every processing step appends a `ProcessingStep` to the provenance chain:
- Stage name (ingestion, extraction, normalization, output)
- Processor name
- Timestamp + duration
- Input/output content hashes
- Error messages if any

## 2-Stage Processing Strategy

### Stage 1: Extraction (Structural Parsing)

Extractors convert raw content into typed `ContentBlock`s:

| Extractor | Input | Output |
|-----------|-------|--------|
| `MinerUExtractor` | PDF binary | Headings, tables, images, text from MinerU markdown |
| `HTMLExtractor` | Confluence HTML | Headings, tables, images, links, code, text |
| `MarkdownExtractor` | Markdown/text | Headings, code blocks, links, images, text |
| `SchemaExtractor` | Athena metadata | Column tables, description text, schema info |

The engine auto-selects the extractor based on content type.

### Stage 2: Normalization (Semantic Enrichment)

Normalizers enrich extracted documents:

| Normalizer | Method | Actions |
|------------|--------|---------|
| `RuleBasedNormalizer` | Deterministic | Abbreviation detection, language detection, word count |
| `LLMNormalizer` | 9Router LLM | Domain classification, entity extraction, quality scoring, summaries |

## Downstream Integration

### Vector Retrieval

```python
doc = CanonicalDocument(...)
chunks = doc.to_embedding_chunks(max_tokens=512, overlap=64)
# Each chunk: {document_id, source_system, title, text, metadata, tags}
```

### Graph Extraction

```python
doc = CanonicalDocument(...)
payload = doc.to_graph_payload()
# Compatible with finx-agentic bootstrap chunk_builder.py
```

### Legacy Format

The `JSONWriter(format="legacy")` produces output matching the existing format consumed by `finx-agentic/scripts/bootstrap/`:
- Confluence: `{page_id, title, url, space, content, items}`
- Schema: `{table_name, database, columns, partition_keys, content}`

## Usage

### CLI

```bash
# Confluence
uv run python -m pipeline.cli confluence --space DAFinX --output output/pipeline

# Local files
uv run python -m pipeline.cli local --dir input/schemas --output output/pipeline

# With LLM normalization
uv run python -m pipeline.cli confluence --space DAFinX --use-llm

# Athena schemas
uv run python -m pipeline.cli athena --database my_db

# S3 documents
uv run python -m pipeline.cli s3 --bucket docs --prefix reports/
```

### Python API

```python
from pipeline.adapters.local import LocalFileAdapter
from pipeline.engine import PipelineEngine, PipelineConfig
from pipeline.writers.json_writer import JSONWriter

adapter = LocalFileAdapter("input/schemas")
writer = JSONWriter("output/pipeline", format="canonical")
config = PipelineConfig(use_llm_normalizer=True)

engine = PipelineEngine(config=config, writer=writer)
result = engine.run(adapter)
result.print_summary()
```

## Idempotency

- `document_id` is deterministic (SHA-256 of source coordinates)
- `ProgressTrackingWriter` maintains a `.pipeline_progress.json` file
- Re-runs skip already-processed documents
- Content hashes in provenance enable change detection

## Error Handling

- Each document processes independently; one failure doesn't stop the pipeline
- Structured `PipelineError` records with category, severity, retryability
- `max_errors` config stops the pipeline after too many failures
- All errors are logged and included in the `PipelineResult` summary

## Testing

```bash
uv run python -m pytest tests/ -v
```

72 tests covering schemas, extractors, normalizers, adapters, writers, and engine integration.
