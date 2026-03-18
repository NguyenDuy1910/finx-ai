import type {
  DiscoverTablesRequest,
  DiscoverTablesResponse,
  TableInfo,
  PreviewDesignRequest,
  PreviewDesignResponse,
  IndexTablesRequest,
  IndexTablesResponse,
  RunPipelineRequest,
  RunPipelineResponse,
  IndexingProgress,
  GraphIndexingStats,
} from "@/types/table-indexing.types";

const BASE = "/api/table-indexing";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || data.detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

/** POST /table-indexing/discover */
export async function discoverTables(
  req: DiscoverTablesRequest
): Promise<DiscoverTablesResponse> {
  const res = await fetch(`${BASE}/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<DiscoverTablesResponse>(res);
}

/** GET /table-indexing/tables/{name} */
export async function getTableDetail(
  tableName: string,
  schemaDir?: string,
  database?: string
): Promise<TableInfo> {
  const params = new URLSearchParams();
  if (schemaDir) params.set("schema_dir", schemaDir);
  if (database) params.set("database", database);
  const qs = params.toString();
  const res = await fetch(`${BASE}/tables/${encodeURIComponent(tableName)}${qs ? `?${qs}` : ""}`);
  return jsonOrThrow<TableInfo>(res);
}

/** POST /table-indexing/preview */
export async function previewDesign(
  req: PreviewDesignRequest
): Promise<PreviewDesignResponse> {
  const res = await fetch(`${BASE}/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<PreviewDesignResponse>(res);
}

/** POST /table-indexing/index */
export async function indexTables(
  req: IndexTablesRequest
): Promise<IndexTablesResponse> {
  const res = await fetch(`${BASE}/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<IndexTablesResponse>(res);
}

/** POST /table-indexing/pipeline */
export async function runPipeline(
  req: RunPipelineRequest
): Promise<RunPipelineResponse> {
  const res = await fetch(`${BASE}/pipeline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return jsonOrThrow<RunPipelineResponse>(res);
}

/** GET /table-indexing/progress */
export async function getIndexingProgress(): Promise<IndexingProgress> {
  const res = await fetch(`${BASE}/progress`);
  return jsonOrThrow<IndexingProgress>(res);
}

/** GET /table-indexing/stats */
export async function getIndexingStats(): Promise<GraphIndexingStats> {
  const res = await fetch(`${BASE}/stats`);
  return jsonOrThrow<GraphIndexingStats>(res);
}
