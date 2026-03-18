# finx-data

Preprocess company data from multiple sources → structured JSON aligned to the Graphiti ontology.

## The Flow

```
input/                         9Router LLM                    output/
(Athena, Confluence,     →    (localhost:20128)           →   (structured JSON
 files, external)              extract entities                per route)
                               aligned to ontology
```

**output/** is what `finx-agentic` reads to build the knowledge graph.

## Setup

```bash
cd finx-data
cp .env.example .env   # set NINE_ROUTER_API_KEY, Confluence creds, etc.
uv sync
```

## Input

Drop raw files into `input/<route>/`:

| Folder | What to put here |
|---|---|
| `input/schemas/` | Athena table schema JSON (or leave empty → reads from Athena live) |
| `input/semantic/` | Metric catalogs, business glossaries (.json or .md) |
| `input/physical/` | Table/column/join documentation |
| `input/query/` | SQL templates, approved patterns |
| `input/governance/` | Access policies, RBAC exports |
| `input/feedback/` | Failure cases, mapping corrections |
| `input/history_questions/` | Historical NL→SQL pairs |
| `input/analyst_feedback/` | Analyst correction forms |
| *(Confluence)* | Set `CONFLUENCE_SPACE_KEYS` in `.env` — fetched live |

## Run

```bash
# All routes
uv run python run_all.py

# Single route
uv run python route_schema.py
uv run python route_confluence.py
uv run python route_semantic.py
# ... etc

# Schema from local files instead of Athena
SCHEMA_INPUT_DIR=input/schemas uv run python route_schema.py
```

## Output

```
output/
├── schema/           ← Table, Column entities
├── semantic/         ← Metric, BusinessTerm, Dimension, KPIFormula
├── physical/         ← Dataset, JoinPath, AggregationGrain
├── query/            ← SQLPattern, ConstraintRule, ExampleQuestion
├── governance/       ← AccessPolicy, UserRole, DataSensitivity
├── feedback/         ← AnalystFeedback, QueryFailureCase
├── confluence/       ← mixed entities extracted from wiki pages
├── history_question/ ← ExampleQuestion, UsageExample
└── analyst_feedback/ ← AnalystFeedback
```

Each file is a single JSON entity matching the Graphiti ontology types.
`finx-agentic` can read this folder directly to index into FalkorDB.
