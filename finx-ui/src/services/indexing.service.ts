import type {
  PreviewRequest,
  PreviewResponse,
  IndexRequest,
  IndexResponse,
  SyncRequest,
  SyncResponse,
  IndexingProgress,
  GraphIndexingStats,
  GlueTablesRequest,
  GlueTablesResponse,
  UsageIndexRequest,
  UsageIndexResponse,
  ExampleQueryRequest,
  ExampleQueryResponse,
  IngestFilesResponse,
  IngestUrlRequest,
  IngestUrlResponse,
  IngestTextRequest,
  IngestTextResponse,
} from "@/types/indexing.types";

const BASE = "/api/indexing";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      data.error || data.detail || `Request failed (${res.status})`
    );
  }
  return res.json() as Promise<T>;
}

export async function previewEnrichment(
  req: PreviewRequest
): Promise<PreviewResponse> {
  const res = await fetch(`${BASE}/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<PreviewResponse>(res);
}

export async function runIndexing(
  req: IndexRequest
): Promise<IndexResponse> {
  const res = await fetch(`${BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<IndexResponse>(res);
}

export async function syncIndexing(
  req: SyncRequest
): Promise<SyncResponse> {
  const res = await fetch(`${BASE}/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<SyncResponse>(res);
}

export async function getIndexingProgress(): Promise<IndexingProgress> {
  const res = await fetch(`${BASE}/progress`);
  return jsonOrThrow<IndexingProgress>(res);
}

export async function getIndexingStats(): Promise<GraphIndexingStats> {
  const res = await fetch(`${BASE}/stats`);
  return jsonOrThrow<GraphIndexingStats>(res);
}

export async function fetchGlueTables(
  req: GlueTablesRequest
): Promise<GlueTablesResponse> {
  const res = await fetch("/api/datasource/glue/tables", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<GlueTablesResponse>(res);
}

/* ── Usage Stats ─────────────────────────────────────────────────── */

export async function runUsageIndexing(
  req: UsageIndexRequest
): Promise<UsageIndexResponse> {
  const res = await fetch(`${BASE}/usage/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<UsageIndexResponse>(res);
}

/* ── Example Queries ─────────────────────────────────────────────── */

export async function runExampleIndexing(
  req: ExampleQueryRequest
): Promise<ExampleQueryResponse> {
  const res = await fetch(`${BASE}/examples/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<ExampleQueryResponse>(res);
}

/* ── Document Ingestion ──────────────────────────────────────────── */

const INGEST_TIMEOUT = 300_000;

function ingestSignal(): AbortSignal {
  return AbortSignal.timeout(INGEST_TIMEOUT);
}

export async function ingestFiles(
  files: File[],
  options?: { entityName?: string; tags?: string[] }
): Promise<IngestFilesResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  if (options?.entityName) form.append("entity_name", options.entityName);
  if (options?.tags?.length) form.append("tags", options.tags.join(","));

  const res = await fetch(`${BASE}/ingest/files`, {
    method: "POST",
    body: form,
    signal: ingestSignal(),
  });
  return jsonOrThrow<IngestFilesResponse>(res);
}

export async function ingestUrl(
  req: IngestUrlRequest
): Promise<IngestUrlResponse> {
  const res = await fetch(`${BASE}/ingest/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal: ingestSignal(),
  });
  return jsonOrThrow<IngestUrlResponse>(res);
}

export async function ingestText(
  req: IngestTextRequest
): Promise<IngestTextResponse> {
  const res = await fetch(`${BASE}/ingest/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal: ingestSignal(),
  });
  return jsonOrThrow<IngestTextResponse>(res);
}
