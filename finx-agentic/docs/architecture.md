# FinX Agentic — Project Architecture

## Overview

FinX Agentic is a multi-agent banking data intelligence system built on the
**Agno** framework. It orchestrates specialist agents to answer natural language
questions over a banking data warehouse (AWS Athena), backed by a knowledge
graph (FalkorDB via Graphiti).

---

## Folder Structure

```
src/
├── agents/                    # Agent factory functions (one file per agent)
│   ├── intent_analyzer.py     # LLM intent pre-analysis + retrieval weight hints
│   ├── knowledge.py           # Knowledge Agent (schema discovery via graph)
│   ├── sql_generator.py       # SQL Generator Agent (Athena SQL + auto-execute)
│   ├── chart_builder.py       # Chart Builder Agent (chart spec generation)
│   ├── confluence_researcher.py # Confluence/Jira research via MCP
│   ├── schema_enricher.py     # LLM schema enricher (used for /indexing/preview)
│   └── hooks/
│       └── sql_auto_execute.py  # Post-hook: extract SQL → execute on Athena
│
├── core/                      # Framework primitives — no business logic
│   ├── graphiti.py            # GraphitiClient (FalkorDB + Graphiti wrapper)
│   ├── model_factory.py       # create_model() / create_model_for_agent()
│   ├── llm_cost_tracker.py    # Token + cost tracking for Graphiti LLM calls
│   ├── tracked_openai.py      # OpenAI client wrapper that records usage
│   ├── exceptions.py          # Domain exceptions
│   ├── types.py               # Pydantic models for schema enrichment pipeline
│   ├── workflow.py            # Re-exports agno Workflow/Step/Condition
│   └── ontology/              # Graph ontology definitions
│       ├── entity_types.py    # Node types (Table, Column, Domain, …)
│       ├── edge_types.py      # Edge types (CONTAINS_COLUMN, BELONGS_TO_DOMAIN, …)
│       └── extraction_config.py  # Graphiti extraction instructions
│
├── knowledge/                 # Knowledge graph access layer
│   ├── graph_knowledge.py     # GraphKnowledgeV2 — agno Knowledge adapter
│   ├── memory.py              # MemoryManager — episode recording + context lookup
│   ├── constants.py           # GROUP_ID, TOP_K, SIMILARITY_THRESHOLD defaults
│   ├── indexing/
│   │   ├── base.py            # IndexingState, GraphitiWriter, PreparedItem
│   │   └── schema_metadata.py # SchemaMetadataWorkflow (agno Workflow for indexing)
│   └── retrieval/
│       ├── native_retrieval.py # NativeRetrieval — main search (embedding + graph)
│       └── reranker.py        # Intent-aware 5-dimension reranker + weight profiles
│
├── prompts/                   # Prompt management
│   ├── manager.py             # PromptManager — Jinja2 singleton
│   └── templates/             # Jinja2 templates per agent
│       ├── knowledge/
│       ├── sql_generator/
│       ├── chart_builder/
│       ├── confluence_researcher/
│       └── schema_enricher/
│
├── storage/
│   └── postgres.py            # get_postgres_db() — agno session/memory storage
│
├── teams/
│   └── finx_team.py           # build_finx_team() — assembles the multi-agent team
│
├── tools/
│   ├── chart_builder.py       # ChartBuilderTools (agno Toolkit)
│   └── mcp_atlassian_tools.py # MCPTools factory for Confluence + Jira
│
├── utils/
│   └── doc_parser.py          # PDF/HTML text extraction for /indexing/upload-context
│
├── web/                       # FastAPI application
│   ├── app.py                 # create_app() — FastAPI + AgentOS assembly
│   └── v1/
│       ├── deps.py            # AppState singleton (GraphitiClient + MemoryManager)
│       ├── routers/           # API endpoints
│       │   ├── health.py
│       │   ├── search.py      # /search/schemas, /search/tables/:name, /search/join-path
│       │   ├── graph.py       # /graph/index, /graph/stats, /graph/feedback
│       │   ├── graph_explorer.py # /graph/explorer — visual graph CRUD
│       │   └── indexing.py    # /indexing/run, /indexing/preview, /indexing/upload-context
│       ├── schemas/           # Pydantic request/response models
│       └── services/          # Service layer between routers and knowledge layer
│           ├── search_service.py
│           ├── indexing_service.py
│           └── graph_explorer_service.py
│
└── workflows/                 # Reserved for future workflow compositions
    └── __init__.py
```

---

## Request Flow

```
User query (any language)
        │
        ▼
  FinX Team (coordinator LLM)
        │
        ├─► Knowledge Agent pre-hook
        │       └── analyze_intent() → intent, domain, weight_hints, english_query
        │
        ├─► Knowledge Agent
        │       └── GraphKnowledgeV2.aretrieve()
        │               └── NativeRetrieval.retrieve()
        │                       ├── Layer 1: embedding vector search (cosine)
        │                       ├── Layer 2: graph neighborhood (domain anchor)
        │                       ├── Layer 3: example/pattern matching
        │                       └── Reranker: intent-weighted scoring
        │
        ├─► SQL Generator Agent
        │       └── Generates SQL in response text
        │               └── sql_auto_execute post-hook
        │                       └── AthenaDirectExecutor → execute on AWS Athena
        │
        └─► Chart Builder Agent (optional)
                └── ChartBuilderTools → returns chart spec JSON
```

---

## Key Design Patterns

### 1. Agent Factory Pattern
Each agent is created via a `create_<name>_agent()` factory function.
Factories accept only what they need (session_id, db, graphiti_client).
No global state in agents.

### 2. Post-hook Execution (SQL)
The SQL Generator Agent writes SQL in its text response.
`sql_auto_execute.py` post-hook extracts the SQL block, executes it on Athena
via boto3, and injects the results back into the response — zero tool-call overhead.

### 3. Pre-hook Intent Analysis (Knowledge)
Before the Knowledge Agent searches the graph, the `_intent_analysis_pre_hook`
runs an LLM call to classify intent and produce retrieval weight hints.
These are stored in `session_state` and picked up by `_build_knowledge_retriever`.

### 4. Workflow-based Indexing
`SchemaMetadataWorkflow` uses agno's `Workflow/Step/Condition` to batch-index
schema payloads into the Graphiti knowledge graph with bulk + single-write fallback.

### 5. Service Layer (API)
Each router delegates to a service class (`SearchService`, `IndexingService`, etc.)
that holds no HTTP state — easy to unit-test independently of FastAPI.

---

## Adding a New Agent

1. Create `src/agents/<name>.py` with a `create_<name>_agent()` factory.
2. Add a Jinja2 template in `src/prompts/templates/<name>/instructions.jinja2`.
3. Add an agent model config in `config/config.json` under `agent_models.<name>`.
4. Register the agent in `src/teams/finx_team.py` → `build_finx_team()`.
5. Export from `src/agents/__init__.py`.

## Adding a New API Endpoint

1. Add request/response Pydantic models to `src/web/v1/schemas/`.
2. Add business logic to the appropriate service in `src/web/v1/services/`.
3. Add the route to the appropriate router in `src/web/v1/routers/`.
4. Include the router in `src/web/app.py` if it's new.
