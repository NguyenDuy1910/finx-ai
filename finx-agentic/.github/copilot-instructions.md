# GitHub Copilot Instructions

## Project Overview

This is **FinX Agentic** — a Python-based agentic AI system for banking data analytics. It uses a multi-agent architecture with knowledge graph (Graphiti), LLM pipelines, and SQL generation to answer natural language questions over a data warehouse.

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: uv
- **Frameworks**: Pydantic, asyncio, OpenAI SDK, Agno (agents/teams/workflows)
- **Knowledge Graph**: Graphiti (FalkorDB-backed)
- **Web**: FastAPI
- **Testing**: pytest

## Code Style

- Line length: **100 characters**
- `from __future__ import annotations` in all modules
- Type hints required on all function signatures
- `async/await` for all I/O-bound operations
- `logging.getLogger(__name__)` — never `print()`
- Pydantic `BaseModel` for API schemas and domain event models

---

## Folder Structure

```
src/
├── core/                        # Framework primitives — shared across ALL features
│   ├── source.py                # IndexingSource ABC + registry helpers
│   ├── exceptions.py            # All custom exceptions
│   ├── types.py                 # Shared type aliases
│   ├── model_factory.py         # LLM model creation
│   ├── tracked_openai.py        # OpenAI client with cost tracking
│   ├── llm_cost_tracker.py      # LLM cost tracker
│   └── graph/
│       ├── client.py            # GraphitiClient (write_episode, write_episodes_bulk, search)
│       └── ontology/            # Entity/edge type definitions
│
├── knowledge/                   # Knowledge graph domain
│   ├── payload.py               # CanonicalEvent, CanonicalEventBatch, EpisodeSourceType
│   ├── retrieval.py             # Graph retrieval logic
│   └── indexing/                # Writing data INTO the graph
│       ├── __init__.py          # Owns: EpisodePayload, PreparedItem. Re-exports public API
│       ├── workflow.py          # IndexingWorkflow — multi-source Agno orchestrator
│       ├── schema_metadata.py   # SchemaMetadataWorkflow + SchemaMetadataSource
│       ├── document_ingestion.py# DocumentIngestionWorkflow + DocumentSource
│       ├── text_ingestion.py    # TextSource (raw text, no LLM extraction)
│       └── utils/
│           ├── text.py          # slugify, split_sections, utc_now
│           ├── readers.py       # File/URL/Confluence readers
│           └── events.py        # Event extraction: infer_route, parse_event_batch,
│                                # normalize_event, event_to_episode, build_extraction_agent
│
├── agents/                      # One file per Agno Agent
│   └── hooks/                   # Agent lifecycle hooks
│
├── teams/                       # Agno Team orchestrations
├── tools/                       # Agno Tool definitions (callable by agents)
├── prompts/                     # Prompt templates
├── storage/                     # Persistence (PostgreSQL)
├── utils/                       # Global pure utilities — no business logic
├── web/
│   ├── app.py                   # FastAPI app factory
│   └── v1/
│       ├── deps.py              # Dependency injection
│       ├── routers/             # HTTP routes — one file per domain, no business logic here
│       ├── schemas/             # Pydantic request/response models per domain
│       └── services/            # Business logic called by routers
└── workflows/                   # Multi-agent workflow orchestrations
```

---

## Strict Rules

### One file = one responsibility
- Each file owns exactly **one concern**: a workflow, a source, a service, a helper set
- Never mix: data models + business logic + IO in one file

### Where things belong
| What | Where |
|---|---|
| Shared primitives (`PreparedItem`, `EpisodePayload`) | `knowledge/indexing/__init__.py` |
| ABC contracts + interfaces | `core/` |
| Registry/lookup helpers | Module-level functions — **NOT** classmethods on ABC |
| Pure helpers (text, math) | `*/utils/<specific_name>.py` |
| Domain event models (Pydantic) | `knowledge/payload.py` |
| API request/response schemas | `web/v1/schemas/<domain>.py` |
| Agno step executors | Same file as the workflow that uses them |
| HTTP business logic | `web/v1/services/` — never in routers |

### Import direction — never reverse
```
web → agents/teams → knowledge → core
                  ↘ tools ↗
```
- `core/` never imports from `knowledge/`, `agents/`, `web/`
- `utils/` never imports from feature modules

### Agno patterns
- Step executor = class with `async def __call__(self, step_input: StepInput) -> StepOutput`
- Condition evaluator = **module-level function** (not a method)
- Workflow-local state = `@dataclass` in same file, private prefix `_` (e.g. `_SchemaState`)
- Each workflow owns its own state dataclass — never share state types across workflows

### Adding a new IndexingSource
1. One file: `knowledge/indexing/<name>_ingestion.py`
2. Class: `class MySource(IndexingSource, source_type="<name>"):`
3. Implement only: `async def prepare(self) -> list[PreparedItem]`
4. Export from `knowledge/indexing/__init__.py`

### Never create
- `models.py` — use `payload.py` for domain models, `__init__.py` for primitives
- `helpers.py` or flat `utils.py` — use `utils/<specific_name>.py`
- God classes that own data + logic + IO together
- Wrapper classes around `GraphitiClient` — call `graph.write_episode` / `graph.write_episodes_bulk` directly
- Tracking/summary/count fields on state dataclasses unless explicitly needed for business logic
