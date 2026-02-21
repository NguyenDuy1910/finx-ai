# Enhanced Text2SQL Architecture – Multi-Agent with Agno Framework

## Overview

This document describes the enhanced Text2SQL architecture inspired by
[WrenAI's AskService](https://deepwiki.com/Canner/WrenAI/3.2-ask-service-and-query-processing),
adapted for the **Agno** multi-agent framework.

---

## Architecture Comparison

### WrenAI AskService (reference)
```
User → AskService.ask()
         ├─ Historical Question Cache
         ├─ Intent Classification Pipeline
         ├─ Schema Retrieval Pipeline
         ├─ SQL Reasoning Pipeline
         ├─ SQL Generation Pipeline
         ├─ SQL Validation Pipeline
         └─ SQL Correction Pipeline (loop)
```

### FinX Enhanced (Agno multi-agent)
```
User → ChatService.chat() / chat_stream()
         │
         ├─ Session Management (create/get/history)
         │
         └─ AskService.ask()
              ├─ TTLCache (historical match)
              ├─ IntentClassifier Agent      ← NEW
              ├─ QueryUnderstanding Agent    (existing, enhanced)
              ├─ SchemaDiscovery Agent       (existing)
              ├─ SQLReasoner Agent           ← NEW
              ├─ SQLGenerator Agent          (existing)
              ├─ Validation Agent            (existing)
              ├─ SQLDiagnoser Agent          ← NEW
              ├─ SQLCorrector Agent          ← NEW
              └─ Learning Agent              (existing)
```

---

## Component Map

### 1. ChatService (`src/web/v1/services/chat_service.py`)

The user-facing layer. Manages multi-turn conversations:

| Feature | Description |
|---------|-------------|
| Session management | Create, list, get, delete sessions |
| History windowing | Keeps last N messages as context |
| Polling mode | `chat()` - waits for complete result |
| Streaming mode | `chat_stream()` - yields SSE events |
| Cancellation | `stop_active_query()` per session |

```
ChatRequest → ChatService → AskRequest → AskService → poll → ChatResponse
```

### 2. AskService (`src/web/v1/services/ask_service.py`)

The orchestration engine. Maps to WrenAI's `AskService`:

| WrenAI Concept | FinX Implementation |
|---|---|
| `TTLCache` for results | `cachetools.TTLCache[str, AskResultResponse]` |
| Status state machine | `AskStatus` enum: understanding→searching→planning→generating→correcting→finished/failed/stopped |
| `_is_stopped()` check | `self._stopped` dict, checked before each stage |
| Pipeline dictionary | Dedicated Agno Agent per stage |
| `@observe` tracing | CostTracker across all steps |
| SSE streaming | `ask_streaming()` async generator |
| Fire-and-forget | `asyncio.create_task(self._run_pipeline(...))` |

### 3. Agents (7 specialized agents)

| Agent | File | WrenAI Equivalent | Purpose |
|---|---|---|---|
| IntentClassifier | `agents/intent_classification.py` | Intent Classification Pipeline | Routes query to TEXT_TO_SQL / SCHEMA_QUERY / GENERAL / CLARIFICATION |
| QueryUnderstanding | `agents/query_understanding.py` | (part of Ask flow) | Parses NL into structured ParsedQuery |
| SchemaDiscovery | `agents/schema_discovery.py` | Schema Retrieval Pipeline | Finds relevant tables, columns, joins |
| SQLReasoner | `agents/sql_reasoning.py` | SQL Generation Reasoning Pipeline | Produces step-by-step plan before SQL |
| SQLGenerator | `agents/sql_generator.py` | SQL Generation Pipeline | Generates the actual SQL query |
| Validation | `agents/validation.py` | SQL Validation Pipeline | Checks SQL correctness |
| SQLDiagnoser | `agents/sql_correction.py` | SQL Diagnosis Pipeline | Analyses error root cause |
| SQLCorrector | `agents/sql_correction.py` | SQL Correction Pipeline | Fixes SQL based on diagnosis |
| Learning | `agents/learning.py` | (post-processing) | Stores successful episodes for future retrieval |

---

## Status State Machine

```
                          ┌──────────┐
                    ┌────►│ STOPPED  │
                    │     └──────────┘
                    │
┌───────────────┐   │   ┌───────────┐   ┌──────────┐   ┌────────────┐
│ UNDERSTANDING ├───┼──►│ SEARCHING ├──►│ PLANNING ├──►│ GENERATING │
└───────────────┘   │   └───────────┘   └──────────┘   └─────┬──────┘
                    │                                         │
                    │   ┌────────────┐   ┌──────────┐         │
                    ├──►│  FAILED    │◄──┤CORRECTING│◄────────┘
                    │   └────────────┘   └─────┬────┘    (if validation fails)
                    │                          │
                    │   ┌──────────┐           │ (if valid after correction)
                    └──►│ FINISHED │◄──────────┘
                        └──────────┘
```

Each transition checks `_is_stopped(query_id)` to support cancellation.

---

## Pipeline Flow (detailed)

### Stage 1: Intent Classification
```python
IntentClassifier Agent
  Input:  query + conversation_history + available_tables
  Output: IntentClassificationResult {
    intent: TEXT_TO_SQL | SCHEMA_QUERY | MISLEADING_QUERY | GENERAL | CLARIFICATION_NEEDED
    confidence: float
    rewritten_query: Optional[str]  # improved version of the query
    clarification_question: Optional[str]
  }
```
- If NOT `TEXT_TO_SQL` → return early with appropriate response
- If `TEXT_TO_SQL` → use `rewritten_query` (if provided) for subsequent stages

### Stage 2: Query Understanding + Schema Retrieval
```python
QueryUnderstanding Agent → ParsedQuery {intent, entities, filters, time_range, ...}
SchemaDiscovery Agent    → SchemaContext {tables, relationships, joins, partitions}
```
- If no relevant schema found → FAIL with `NO_RELEVANT_DATA`

### Stage 3: SQL Reasoning (optional)
```python
SQLReasoner Agent → SQLReasoningPlan {
  steps: ["1. Start from account table", "2. Join with transaction...", ...]
  tables_needed, joins_needed, filters_needed, aggregations_needed
}
```
- Can be skipped via `ignore_sql_reasoning=True` or config flag
- Supports SSE streaming for real-time "thinking" display

### Stage 4: SQL Generation
```python
SQLGenerator Agent → GeneratedSQL {sql, database, reasoning, tables_used, ...}
```
- Receives schema context + reasoning plan + conversation history

### Stage 5: Validation + Correction Loop
```python
for attempt in 1..max_retries:
    Validation Agent → ValidationResult {is_valid, errors, corrected_sql}
    if valid: DONE
    SQLDiagnoser Agent → SQLDiagnosisResult {error_type, root_cause, suggestion}
    if TIMEOUT: break
    SQLCorrector Agent → SQLCorrectionResult {corrected_sql, reasoning}
    # Re-validate...
```

### Stage 6: Learning (background)
```python
Learning Agent → stores episode in knowledge graph (fire-and-forget)
```

---

## API Endpoints

### Ask (low-level, async)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/ask` | Submit query, returns `query_id` |
| GET | `/api/v1/ask/{query_id}` | Poll for result |
| POST | `/api/v1/ask/{query_id}/stop` | Cancel query |
| GET | `/api/v1/ask/{query_id}/stream` | SSE stream |

### Chat (high-level, session-aware)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/chat` | Send message, wait for response |
| POST | `/api/v1/chat/stream` | Send message, get SSE events |
| POST | `/api/v1/chat/sessions` | Create session |
| GET | `/api/v1/chat/sessions` | List sessions |
| GET | `/api/v1/chat/sessions/{id}` | Get session + history |
| DELETE | `/api/v1/chat/sessions/{id}` | Delete session |
| POST | `/api/v1/chat/sessions/{id}/stop` | Cancel active query |

---

## Key Design Decisions

### 1. Agent-per-stage (not Agno Team)
Each pipeline stage uses a **dedicated Agent** rather than an Agno `Team`.
This gives us:
- Deterministic execution order (vs. Team's dynamic routing)
- Precise status tracking per stage
- Granular cost tracking per agent
- The ability to skip stages via feature flags

The existing `finx_team.py` `Team` remains for the **interactive playground**
where the user expects free-form conversation with dynamic agent selection.

### 2. Fire-and-forget with TTLCache
Like WrenAI, `ask()` returns immediately with a `query_id`. The pipeline
runs as an `asyncio.create_task`. Clients poll or stream. Results expire
after `ttl` seconds to prevent stale data.

### 3. Separation: ChatService vs AskService
- **AskService** = stateless query processor (one query at a time)
- **ChatService** = stateful session manager (multi-turn, history)

This mirrors the WrenAI separation where the Ask service handles individual
queries and the UI layer manages conversations.

### 4. Correction loop with diagnosis
Inspired by WrenAI's `allow_sql_diagnosis` flag. The diagnosis agent
provides targeted error analysis before the correction agent attempts a fix.
This produces better corrections than blind retry.

---

## File Structure (new/modified)

```
src/
├── agents/
│   ├── intent_classification.py    ← NEW
│   ├── sql_reasoning.py            ← NEW
│   ├── sql_correction.py           ← NEW
│   ├── query_understanding.py      (existing)
│   ├── schema_discovery.py         (existing)
│   ├── sql_generator.py            (existing)
│   ├── validation.py               (existing)
│   ├── learning.py                 (existing)
│   └── __init__.py                 (updated)
├── core/
│   ├── ask_types.py                ← NEW
│   ├── types.py                    (existing)
│   └── cost_tracker.py             (existing)
├── prompts/templates/
│   ├── intent_classification/      ← NEW
│   │   ├── instructions.jinja2
│   │   └── classify.jinja2
│   ├── sql_reasoning/              ← NEW
│   │   ├── instructions.jinja2
│   │   └── reason.jinja2
│   └── sql_correction/             ← NEW
│       ├── diagnosis_instructions.jinja2
│       ├── correction_instructions.jinja2
│       ├── diagnose.jinja2
│       └── correct.jinja2
└── web/v1/
    ├── routers/
    │   └── ask.py                  ← NEW
    ├── services/
    │   ├── ask_service.py          ← NEW
    │   └── chat_service.py         ← NEW
    └── app.py                      (updated - added ask router)
```

---

## Usage Examples

### Polling mode (frontend)
```javascript
// 1. Submit query
const { query_id } = await fetch('/api/v1/ask', {
  method: 'POST',
  body: JSON.stringify({ query: "How many active accounts last month?" })
}).then(r => r.json());

// 2. Poll until done
let result;
do {
  result = await fetch(`/api/v1/ask/${query_id}`).then(r => r.json());
  // Update UI with result.status: understanding → searching → planning → generating
} while (!['finished', 'failed', 'stopped'].includes(result.status));
```

### Streaming mode (EventSource)
```javascript
const es = new EventSource(`/api/v1/ask/${query_id}/stream`);
es.addEventListener('status', (e) => updateStatusUI(JSON.parse(e.data)));
es.addEventListener('done', (e) => showResult(JSON.parse(e.data)));
```

### Chat mode (simple)
```javascript
const response = await fetch('/api/v1/chat', {
  method: 'POST',
  body: JSON.stringify({
    message: "How many users registered yesterday?",
    session_id: "abc-123",
  })
}).then(r => r.json());
// response.sql, response.reasoning, response.tables_used
```
