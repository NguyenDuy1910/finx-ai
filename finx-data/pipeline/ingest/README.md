# finx-data · Qdrant Ingestion Stage

Reads preprocessed knowledge files from `output/knowledge/` and upserts them into a Qdrant collection as dense vector embeddings.

## What this step does

1. Loads all `*.json` files from the knowledge output directory
2. Creates or validates the Qdrant collection (COSINE distance, configurable dim)
3. For each document, computes a deterministic UUID point ID from `document_id`
4. Skips documents whose text content hasn't changed since the last run (via `content_hash`)
5. Embeds remaining texts via the OpenAI Embeddings API
6. Upserts points into Qdrant with a rich filterable payload
7. Logs counts: loaded / skipped / embedded / upserted / failed

## Required environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for embeddings |
| `QDRANT_URL` | No | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | No | — | Qdrant API key (cloud deployments) |
| `QDRANT_COLLECTION` | No | `finx_knowledge` | Target collection name |
| `EMBEDDING_MODEL` | No | `text-embedding-3-small` | OpenAI embedding model |

Set these in `.env` (loaded automatically by `python-dotenv`).

## How to run locally

```bash
# 1. Start Qdrant
docker run -p 6333:6333 qdrant/qdrant

# 2. Install deps (from finx-data/)
uv pip install -e .

# 3. Dry run — no writes
uv run python -m pipeline.cli qdrant \
  --knowledge-dir output/knowledge \
  --dry-run

# 4. Full ingestion
uv run python -m pipeline.cli qdrant \
  --knowledge-dir output/knowledge

# 5. Custom collection / model
uv run python -m pipeline.cli qdrant \
  --knowledge-dir output/knowledge \
  --qdrant-url http://qdrant.internal:6333 \
  --collection my_collection \
  --embedding-model text-embedding-3-large \
  --embedding-dim 3072
```

## Rerun safety (idempotency)

The pipeline is safe to rerun multiple times:

- Point IDs are deterministic: `SHA256(source_system::source_uri)[:32]` formatted as UUID
- On each run, existing points are retrieved and their `content_hash` is compared to the current text
- Documents with unchanged text are skipped (no re-embedding, no API cost, no overwrite)
- Use `--overwrite` to force re-embed all documents regardless of hash

## CLI flags

```
--knowledge-dir   Path to knowledge JSON files      (default: output/knowledge)
--qdrant-url      Qdrant server URL                 (default: $QDRANT_URL)
--api-key         Qdrant API key                    (default: $QDRANT_API_KEY)
--collection      Collection name                   (default: $QDRANT_COLLECTION)
--embedding-model OpenAI model name                 (default: text-embedding-3-small)
--embedding-dim   Vector dimension                  (default: 1536)
--batch-size      Points per upsert call            (default: 100)
--min-quality     Skip docs below quality score     (default: 0.0 = no filter)
--overwrite       Re-embed even if content unchanged
--dry-run         Print summary without writing
--log-level       DEBUG / INFO / WARNING / ERROR    (default: INFO)
```

## Architecture decisions

| Decision | Rationale |
|---|---|
| One-doc-one-point | Knowledge files are already LLM-enriched summaries; chunking would destroy semantic unity |
| `text-embedding-3-small` | Already a dependency; good multilingual coverage (Vietnamese + English); swap via `--embedding-model` |
| COSINE distance | Standard for normalized text embeddings |
| UUID from `document_id` | Deterministic, stable across reruns |
| `content_hash` in payload | Enables skip-on-rerun to avoid redundant API calls |
| No `structured_content`/`tables` in payload | Too large for payload filtering; still available in source JSON files on disk |

## Payload fields indexed for filtering

| Field | Type |
|---|---|
| `source_system` | keyword |
| `document_type` | keyword |
| `language` | keyword |
| `space_key` | keyword |
| `domains` | keyword (array) |
| `quality_score` | float |
| `processed_at` | keyword (ISO string) |
| `ingestion_timestamp` | keyword (ISO string) |

## Limitations / follow-up improvements

- **Token limit**: texts longer than ~32 000 characters are truncated before embedding. For very large documents, consider chunking using `CanonicalDocument.to_embedding_chunks()`.
- **Chunked ingestion**: if retrieval quality is poor on long documents, add an optional chunking mode (not implemented yet).
- **Sparse/hybrid retrieval**: dense-only is sufficient for current use; BM25 or sparse vectors can be added later.
- **Embedding provider**: only OpenAI is implemented; swap via the `EmbeddingProvider` ABC in `embedder.py`.
