# FinX AI — Banking Data Intelligence Platform

> A modular AI agent system that combines **Graph-RAG knowledge retrieval**, **Text-to-SQL generation**, and an **interactive Knowledge Graph Explorer** to help banking teams understand and query their data through natural language.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Monorepo Structure](#monorepo-structure)
- [Graph Database Design](#graph-database-design)
  - [Node Types](#node-types)
  - [Edge Types (Relationships)](#edge-types-relationships)
  - [Graph Data Model Diagram](#graph-data-model-diagram)
- [RAG Knowledge Pipeline](#rag-knowledge-pipeline)
  - [Indexing Pipeline](#1-indexing-pipeline)
  - [Retrieval Pipeline (Graph-RAG)](#2-retrieval-pipeline-graph-rag)
  - [Agent Orchestration](#3-agent-orchestration)
- [Sub-Projects](#sub-projects)
  - [finx-agentic (Backend)](#finx-agentic--backend)
  - [finx-ui (Frontend)](#finx-ui--frontend)
  - [finx-mcp (MCP Server)](#finx-mcp--mcp-server)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         finx-ui (Next.js 16)                        │
│  ┌──────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │   Chat   │  │  Playground │  │   Explore   │  │ Admin Panel  │  │
│  │ (AI SDK) │  │  (SQL Lab)  │  │ (Data View) │  │ Graph Explorer│  │
│  └────┬─────┘  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘  │
│       └────────────────┴────────────────┴────────────────┘          │
│                                │ REST API                           │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
┌────────────────────────────────┼────────────────────────────────────┐
│                    finx-agentic (FastAPI)                            │
│                                │                                    │
│  ┌─────────────────────────────▼──────────────────────────────┐     │
│  │               FinX Team (Agno Multi-Agent)                  │     │
│  │  ┌─────────────────┐ ┌──────────────┐ ┌─────────────────┐  │     │
│  │  │ Knowledge Agent │→│  SQL Agent   │→│ Chart Builder   │  │     │
│  │  │ (Graph-RAG)     │ │ (Text2SQL)   │ │ (Vega-Lite)     │  │     │
│  │  └────────┬────────┘ └──────┬───────┘ └─────────────────┘  │     │
│  └───────────┼─────────────────┼──────────────────────────────┘     │
│              │                 │                                    │
│  ┌───────────▼────────┐  ┌────▼──────────────┐                     │
│  │  GraphKnowledge     │  │  finx-mcp (MCP)   │                     │
│  │  SchemaRetrieval    │  │  Athena Provider   │                     │
│  │  + Reranker         │  │  (SQL execution)   │                     │
│  └───────────┬────────┘  └───────────────────┘                     │
│              │                                                      │
│  ┌───────────▼────────────────────────────────────────────────┐     │
│  │            FalkorDB (Graph Database)                        │     │
│  │   Nodes: Domain, Table, Column, BusinessEntity,             │     │
│  │          BusinessRule, CodeSet, QueryPattern                 │     │
│  │   Edges: 13 relationship types                              │     │
│  │   + Vector embeddings (text-embedding-3-large, 3072d)       │     │
│  └────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Monorepo Structure

```
finx-ai/
├── finx-agentic/          # Python backend — FastAPI + Agno agents + Graph-RAG
│   ├── src/
│   │   ├── agents/        # Knowledge, SQL Generator, Chart Builder agents
│   │   ├── core/          # Model factory, cost tracking, types
│   │   ├── knowledge/     # Graph DB client, schemas, indexing, retrieval
│   │   ├── prompts/       # Jinja2 prompt templates
│   │   ├── teams/         # FinX multi-agent team orchestration
│   │   ├── tools/         # Athena executor, graph tools
│   │   └── web/           # FastAPI app, routers, services
│   ├── scripts/           # Schema builder, graph loader, incremental sync
│   └── config/            # Runtime configuration
│
├── finx-ui/               # Next.js 16 frontend — React 19 + ReactFlow
│   └── src/
│       ├── app/           # App Router (single-page SPA with URL sync)
│       ├── components/    # Chat, Admin, Graph Explorer, UI kit
│       ├── hooks/         # useNavPage, useGraphData, useGraphSession
│       ├── services/      # API client functions
│       └── types/         # TypeScript type definitions
│
├── finx-mcp/              # MCP server — Athena SQL execution provider
│   └── src/
│       ├── core/          # MCP types & config
│       ├── providers/     # Athena provider implementation
│       └── registry/      # Provider registry
│
└── docs/                  # PRD & architecture documentation
```

---

## Graph Database Design

The knowledge graph is stored in **FalkorDB** (Redis-compatible graph DB) and managed through **Graphiti Core**. It models the full banking data landscape — from high-level business domains down to individual columns and business rules.

### Node Types

| Node Label | Description | Key Attributes |
|---|---|---|
| **Domain** | Business domain grouping (e.g. "Payment", "Account", "Card") | `name`, `summary`, `attributes` |
| **Table** | Athena/data warehouse table | `name`, `summary`, `database`, `attributes` |
| **Column** | Individual table column | `name`, `summary`, `data_type`, `is_partition`, `attributes` |
| **BusinessEntity** | Semantic business concept (e.g. "Customer", "Transaction") | `name`, `summary`, `attributes` |
| **BusinessRule** | Data validation or business logic rule | `name`, `summary`, `rule_type`, `attributes` |
| **CodeSet** | Enumerated value sets (e.g. status codes, type codes) | `name`, `summary`, `codes`, `attributes` |
| **QueryPattern** | Learned SQL patterns from user queries | `name`, `summary`, `sql_template`, `attributes` |

All nodes carry:
- `uuid` — unique identifier
- `name` — display name
- `summary` — natural language description
- `embedding` — 3072-dim vector from `text-embedding-3-large`
- `group_id` — multi-tenant isolation key
- `created_at` / `updated_at` — timestamps

### Edge Types (Relationships)

| Edge Type | Source → Target | Description |
|---|---|---|
| `BELONGS_TO_DOMAIN` | Table → Domain | Table is part of a business domain |
| `CONTAINS_ENTITY` | Domain → BusinessEntity | Domain contains a business entity |
| `HAS_COLUMN` | Table → Column | Table has a column |
| `JOIN` | Table → Table | Tables can be joined |
| `FOREIGN_KEY` | Table → Table | Foreign key relationship |
| `COLUMN_MAPPING` | Column → BusinessEntity | Column maps to a business concept |
| `ENTITY_MAPPING` | BusinessEntity → Table | Entity is stored in a table |
| `HAS_RULE` | BusinessEntity → BusinessRule | Entity has a business rule |
| `APPLIES_TO` | BusinessRule → Table | Rule applies to a table |
| `HAS_CODESET` | Column → CodeSet | Column uses a code set |
| `DERIVED_FROM` | Column → Column | Column is derived from another |
| `SYNONYM` | BusinessEntity → BusinessEntity | Equivalent business terms |
| `QUERY_USES_TABLE` | QueryPattern → Table | Query pattern references a table |

All edges carry:
- `uuid`, `fact` (natural language description), `embedding`, `group_id`, `created_at`

### Graph Data Model Diagram

```
                            ┌──────────────┐
                            │   Domain     │
                            │ (Payment,    │
                            │  Account...) │
                            └──┬───────┬───┘
              BELONGS_TO_DOMAIN│       │CONTAINS_ENTITY
                               │       │
                ┌──────────────▼─┐   ┌─▼───────────────┐
                │     Table      │   │ BusinessEntity   │
                │ (transaction,  │◄──┤ (Customer,       │
                │  account...)   │   │  Transaction...) │
                └──┬──────┬──┬───┘   └──┬──────────┬────┘
          HAS_COLUMN│  JOIN│  │FK        │HAS_RULE  │SYNONYM
                    │      │  │          │          │
              ┌─────▼──┐   │  │    ┌─────▼────┐     │
              │ Column  │   │  │    │ Business │     │
              │ (id,    │   │  │    │  Rule    │     │
              │  name,  │   │  │    └──────────┘     │
              │  amt..) │   │  │                     │
              └──┬───┬──┘   │  │                     │
     COLUMN_MAPPING  │      │  │                     │
                │  HAS_CODESET │                     │
                │    │      │  │                     │
                │  ┌─▼────┐ │  │              ┌──────▼──────────┐
                │  │CodeSet│ │  │              │ BusinessEntity  │
                │  │(codes)│ │  │              │   (synonym)     │
                │  └──────┘ │  │              └─────────────────┘
                │           │  │
                │     ┌─────▼──▼───┐
                │     │   Table    │
                │     │  (joined)  │
                │     └────────────┘
                │
           ┌────▼──────────┐
           │ QueryPattern   │──── QUERY_USES_TABLE ───→ Table
           │ (learned SQL)  │
           └────────────────┘
```

---

## RAG Knowledge Pipeline

The system implements a **Graph-RAG** (Retrieval-Augmented Generation) architecture where the knowledge graph serves as both a structured knowledge base and a vector search index.

### 1. Indexing Pipeline

```
  Athena (Data Warehouse)
          │
          ▼
  ┌─────────────────────┐     ┌──────────────────────┐
  │ AthenaSchemaReader   │────▶│  DomainGenerator     │
  │ (reads DDL, columns) │     │  (LLM: GPT-4o-mini)  │
  └─────────────────────┘     │  - infers domains     │
                               │  - generates summaries│
                               │  - maps business terms│
                               └──────────┬───────────┘
                                          │ JSON schemas
                                          ▼
                               ┌──────────────────────┐
                               │  SchemaIndexer        │
                               │  EntityIndexer        │
                               │  EpisodeIndexer       │
                               └──────────┬───────────┘
                                          │
                                          ▼
                               ┌──────────────────────┐
                               │  FalkorDB             │
                               │  - Nodes + edges      │
                               │  - Vector indices     │
                               │  - Full-text indices  │
                               └──────────────────────┘
```

**Key indexing features:**
- **Auto-schema discovery**: Reads all tables/columns from Athena automatically
- **LLM-powered enrichment**: GPT-4o-mini generates domain assignments, business entity mappings, summaries, and business rules
- **Incremental sync**: Detects schema changes and updates only what changed
- **Vector embeddings**: Every node/edge gets a 3072-dim embedding for semantic search
- **Cost tracking**: Tracks LLM token usage and embedding costs per operation

### 2. Retrieval Pipeline (Graph-RAG)

```
  User Query: "What tables have customer transaction data?"
          │
          ▼
  ┌─────────────────────────────────────────────────────┐
  │               SchemaRetrievalService                 │
  │                                                      │
  │  1. Vector Search  ──→ Find semantically similar     │
  │     (embedding)        nodes by cosine similarity    │
  │                                                      │
  │  2. Graph Traversal ──→ Follow edges to discover     │
  │     (Cypher queries)    related tables, columns,     │
  │                         domains, rules               │
  │                                                      │
  │  3. Full-text Search ──→ Exact name/keyword match    │
  │     (FalkorDB index)                                 │
  │                                                      │
  │  4. Reranker ──────────→ Score & rank candidates     │
  │     (weighted fusion)    by relevance, recency,      │
  │                          schema completeness         │
  │                                                      │
  │  Output: Ranked list of TableContext with full        │
  │          column details, joins, rules, entities       │
  └─────────────────────────────────────────────────────┘
```

**Retrieval strategies:**
- **Hybrid search**: Combines vector similarity + full-text + graph traversal
- **Multi-hop reasoning**: Follows relationships (e.g., query mentions "payment" → finds Domain → follows `BELONGS_TO_DOMAIN` → finds Tables → follows `HAS_COLUMN` → finds Columns)
- **Reranking**: `SearchReranker` with configurable weights fuses multiple signal sources
- **Early stopping**: If a high-confidence match (≥0.90) is found, skips further search
- **Episode memory**: Past queries and feedback are stored as episodes for learning

### 3. Agent Orchestration

```
  User Question
       │
       ▼
  ┌────────────────────────────────────────┐
  │          FinX Team (Coordinator)        │
  │  Routes request to specialist agents    │
  └────┬──────────────┬────────────────┬───┘
       │              │                │
       ▼              ▼                ▼
  ┌──────────┐  ┌───────────┐  ┌─────────────┐
  │Knowledge │  │SQL Agent  │  │Chart Builder│
  │ Agent    │  │           │  │             │
  │          │  │ Text2SQL  │  │ Vega-Lite   │
  │ Graph-RAG│  │ + Athena  │  │ spec gen    │
  │ retrieval│  │ execution │  │             │
  └──────────┘  └───────────┘  └─────────────┘

  Pipeline: Knowledge → SQL → Chart (sequential, at most once each)
```

**Agent roles:**
| Agent | Purpose | Tools |
|---|---|---|
| **Knowledge Agent** | Discovers relevant schemas, tables, columns, business rules via Graph-RAG | `GraphKnowledge` (auto-retrieval) |
| **SQL Generator Agent** | Converts natural language → SQL, auto-executes on Athena | `AthenaDirectExecutor` via MCP |
| **Chart Builder Agent** | Generates Vega-Lite chart specifications from query results | Chart spec builder |

---

## Sub-Projects

### finx-agentic — Backend

**FastAPI** application with multi-agent AI system.

| Layer | Key Components |
|---|---|
| **Web** | FastAPI routers: `/api/v1/search`, `/api/v1/graph/*`, `/api/v1/graph/explorer/*`, `/health` |
| **Agents** | Knowledge, SQL Generator, Chart Builder — coordinated by FinX Team |
| **Knowledge** | Graph client, schemas (7 node types, 13 edge types), memory manager |
| **Indexing** | Schema indexer, entity indexer, episode indexer |
| **Retrieval** | Schema retrieval (hybrid search), entity queries, graph mutations, reranker |
| **Tools** | Athena SQL executor, graph tools |

### finx-ui — Frontend

**Next.js 16** (App Router) + **React 19** SPA.

| Feature | Description |
|---|---|
| **Chat** | AI conversation interface using Vercel AI SDK |
| **Graph Explorer** | Interactive knowledge graph visualization (ReactFlow + dagre layout) |
| **Admin Panel** | Schema indexing, graph stats, feedback, graph CRUD operations |
| **URL Routing** | SPA with `history.pushState` URL sync (`/chat`, `/admin/graph-explorer`, etc.) |
| **Session Persistence** | Graph explorer state persisted via `sessionStorage` |

### finx-mcp — MCP Server

**Model Context Protocol** server providing SQL execution tools to agents.

| Component | Description |
|---|---|
| **Athena Provider** | Executes SQL queries against AWS Athena |
| **Registry** | Provider registry for pluggable MCP tool providers |
| **Transport** | Supports both stdio and SSE transports |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 16, React 19, TypeScript 5, Tailwind CSS v4, ReactFlow v12, dagre |
| **Backend** | Python 3.12, FastAPI, Agno framework, Pydantic v2 |
| **Graph DB** | FalkorDB (Redis-compatible) via Graphiti Core |
| **Embeddings** | OpenAI `text-embedding-3-large` (3072 dimensions) |
| **LLM** | Configurable via LiteLLM (GPT-4o, GPT-4o-mini, Gemini) |
| **Data Warehouse** | AWS Athena (Presto SQL) |
| **MCP** | Model Context Protocol for tool interop |
| **Observability** | AgentOps, LangTrace, custom cost tracking |

---

## Getting Started

### Prerequisites

- Python ≥ 3.12, Node.js ≥ 20, FalkorDB instance
- AWS credentials (for Athena access)
- OpenAI API key (for embeddings & LLM)

### Backend

```bash
cd finx-agentic
uv sync                    # install dependencies
cp .env.example .env       # configure environment variables
python run_api.py          # start API on :8080
```

### Frontend

```bash
cd finx-ui
npm install
npm run dev                # start dev server on :3000
```

### MCP Server

```bash
cd finx-mcp
uv sync
python server.py --sse     # start MCP SSE server on :8000
```

### Build Knowledge Graph

```bash
cd finx-agentic

# 1. Generate graph schemas from Athena DDL
python scripts/run_load_schemas.py

# 2. Initialize graph DB and load schemas
python scripts/run_init_graph.py

# 3. (Optional) Incremental sync for schema changes
python scripts/run_incremental_sync.py
```
