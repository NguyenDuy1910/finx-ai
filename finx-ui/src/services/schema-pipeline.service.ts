/**
 * Schema Pipeline Service
 * Orchestrates the full pipeline: Connect → Discover → Enrich → Preview → Index
 */

import type {
  ConnectionConfig,
  ContextDocument,
  PipelineTableInfo,
  TableEnrichment,
  TablePreviewResult,
  PipelineIndexResult,
} from "@/types/schema-pipeline.types";

const INDEXING_BASE = "/api/indexing";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      data.error || data.detail || `Request failed (${res.status})`
    );
  }
  return res.json() as Promise<T>;
}

// ── Step 1: Discover tables from source ────────────────────────────

export interface DiscoverResult {
  total_tables: number;
  indexed_tables: number;
  not_indexed_tables: number;
  outdated_tables: number;
  tables: PipelineTableInfo[];
  errors: string[];
}

export async function discoverFromSource(
  config: ConnectionConfig
): Promise<DiscoverResult> {
  const res = await fetch(`${INDEXING_BASE}/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      database: config.database || undefined,
      region: config.region || "ap-southeast-1",
      profile: config.profile || undefined,
    }),
  });
  return jsonOrThrow<DiscoverResult>(res);
}

// ── Step 2: Get single table detail ────────────────────────────────

export async function getTableSchema(
  tableName: string,
  config: ConnectionConfig
): Promise<PipelineTableInfo> {
  const params = new URLSearchParams();
  if (config.database) params.set("database", config.database);
  const qs = params.toString();
  const res = await fetch(
    `${INDEXING_BASE}/tables/${encodeURIComponent(tableName)}${qs ? `?${qs}` : ""}`
  );
  return jsonOrThrow<PipelineTableInfo>(res);
}

// ── Step 2.5: Upload a context document and get extracted text ───────────

export interface UploadContextResult {
  text: string;
  char_count: number;
  source_name: string;
}

export async function uploadContextDocument(
  file: File
): Promise<UploadContextResult> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  const res = await fetch(`${INDEXING_BASE}/upload-context`, {
    method: "POST",
    body: formData,
  });
  return jsonOrThrow<UploadContextResult>(res);
}

export interface FetchUrlResult {
  text: string;
  char_count: number;
  source_name: string;
  is_confluence: boolean;
}

export interface FetchUrlParams {
  url: string;
  confluence_base_url?: string;
  confluence_username?: string;
  confluence_api_token?: string;
}

export async function fetchUrlContent(
  params: FetchUrlParams
): Promise<FetchUrlResult> {
  const res = await fetch(`${INDEXING_BASE}/fetch-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return jsonOrThrow<FetchUrlResult>(res);
}

// ── Step 3: Preview AI design for a single table ────────────────────

export async function previewTableDesign(
  tableName: string,
  config: ConnectionConfig,
  enrichment?: TableEnrichment,
  tableInfo?: PipelineTableInfo,
  contextDocuments?: ContextDocument[],
  otherSelectedTables?: string[]
): Promise<TablePreviewResult> {
  // Build a TableSchema object matching the backend PreviewRequest schema
  const tableSchema = {
    name: tableName,
    database: config.database || "",
    description:
      enrichment?.custom_description ||
      tableInfo?.description ||
      "",
    columns: (tableInfo?.columns ?? []).map((c) => {
      const colOverride = enrichment?.column_overrides?.[c.name];
      return {
        name: c.name,
        data_type: c.data_type,
        description:
          colOverride?.custom_description ||
          c.custom_description ||
          c.description ||
          "",
        is_partition: c.is_partition ?? false,
      };
    }),
    location: tableInfo?.location || "",
    storage_format: tableInfo?.storage_format || "",
    partition_keys: tableInfo?.partition_keys || [],
    row_count: tableInfo?.row_count ?? null,
  };

  // Merge context documents into a single text block for the backend prompt
  const allDocs = [
    ...(enrichment?.context_documents ?? []),
    ...(contextDocuments ?? []),
  ];
  const contextText = allDocs
    .map((d) => d.text)
    .filter(Boolean)
    .join("\n\n---\n\n");

  const contextTables: string[] = (otherSelectedTables ?? []).filter(
    (n) => n !== tableName
  );

  // Use AbortController to enforce a timeout for large-metadata tables
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000); // 120s for LLM enrichment

  let res: Response;
  try {
    res = await fetch(`${INDEXING_BASE}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        table_schema: tableSchema,
        context_tables: contextTables,
        context_text: contextText,
      }),
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        `Preview timed out for table "${tableName}" — the table may have too many columns. ` +
        "Try reducing context or splitting the table."
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

  const data = await jsonOrThrow<{
    name: string;
    database: string;
    description?: string;
    ai_description?: string;
    entity_name?: string;
    domain?: string;
    synonyms?: string[];
    tags?: string[];
    enriched_columns?: Array<{
      name: string;
      data_type: string;
      description: string;
      ai_description?: string;
      business_terms: string[];
      is_primary_key: boolean;
      is_foreign_key: boolean;
      column_type: string;
      foreign_key_ref: string;
    }>;
    relationships?: Array<{
      source_table: string;
      target_table: string;
      relationship_type: string;
      source_column: string;
      target_column: string;
      description: string;
    }>;
    kg_nodes?: Array<{
      id: string;
      label: string;
      type: string;
      description?: string;
    }>;
    kg_edges?: Array<{
      source: string;
      target: string;
      label: string;
      type: string;
    }>;
    llm_cost?: {
      input_tokens: number;
      output_tokens: number;
      cost_usd: number;
      duration_s: number;
    };
  }>(res);

  // Map backend PreviewResponse → frontend TablePreviewResult
  return {
    table_name: data.name,
    database: data.database,
    table_description: data.description || "",
    ai_description: data.ai_description || "",
    entity_name: data.entity_name || "",
    domain: data.domain || "",
    synonyms: data.synonyms || [],
    tags: data.tags || [],
    columns: (data.enriched_columns || []).map((c) => ({
      name: c.name,
      data_type: c.data_type,
      description: c.ai_description || c.description,
      business_terms: c.business_terms,
      is_primary_key: c.is_primary_key,
      is_foreign_key: c.is_foreign_key,
      column_type: c.column_type,
      foreign_key_ref: c.foreign_key_ref,
    })),
    relationships: data.relationships || [],
    kg_nodes: data.kg_nodes || [],
    kg_edges: data.kg_edges || [],
    llm_cost: data.llm_cost || {
      input_tokens: 0,
      output_tokens: 0,
      cost_usd: 0,
      duration_s: 0,
    },
    status: "done",
  };
}

// ── Step 4: Index selected tables ──────────────────────────────────

export async function indexSelectedTables(
  tableNames: string[],
  config: ConnectionConfig,
  previews: Record<string, TablePreviewResult>,
  discoveredTables?: PipelineTableInfo[],
): Promise<PipelineIndexResult> {
  const tables = tableNames.map((name) => {
    const tableInfo = discoveredTables?.find((t) => t.name === name);
    const preview = previews[name];

    const baseColumns = (tableInfo?.columns ?? []).map((c) => ({
      name: c.name,
      data_type: c.data_type,
      description: c.description || "",
      is_partition: c.is_partition ?? false,
      is_primary_key: false,
      sample_values: [],
    }));

    if (!preview || preview.status !== "done") {
      return {
        name,
        database: config.database || tableInfo?.database || "",
        description: tableInfo?.description || "",
        columns: baseColumns,
        location: tableInfo?.location || "",
        storage_format: tableInfo?.storage_format || "",
        partition_keys: tableInfo?.partition_keys || [],
        row_count: tableInfo?.row_count ?? null,
      };
    }

    return {
      name,
      database: preview.database || config.database || "",
      description: preview.table_description || "",
      columns: baseColumns,
      location: tableInfo?.location || "",
      storage_format: tableInfo?.storage_format || "",
      partition_keys: tableInfo?.partition_keys || [],
      row_count: tableInfo?.row_count ?? null,
      entity_name: preview.entity_name || "",
      domain: preview.domain || "",
      synonyms: preview.synonyms || [],
      tags: preview.tags || [],
      ai_description: preview.ai_description || "",
      enriched_columns: (preview.columns ?? []).map((col) => ({
        name: col.name,
        data_type: col.data_type,
        description: col.description || "",
        is_partition: false,
        is_primary_key: col.is_primary_key ?? false,
        sample_values: [],
        ai_description: col.description || "",
        business_terms: col.business_terms || [],
        column_type: col.column_type || "",
      })),
      relationships: (preview.relationships ?? []).map((rel) => ({
        source_table: rel.source_table,
        target_table: rel.target_table,
        relationship_type: rel.relationship_type,
        source_column: rel.source_column || "",
        target_column: rel.target_column || "",
        description: rel.description || "",
      })),
      kg_nodes: preview.kg_nodes || [],
      kg_edges: preview.kg_edges || [],
    };
  });

  const res = await fetch(`${INDEXING_BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tables }),
  });
  return jsonOrThrow<PipelineIndexResult>(res);
}

// ── Progress polling ───────────────────────────────────────────────

export interface IndexingProgressInfo {
  total: number;
  completed: number;
  failed: number;
  current_table: string;
  status:
  | "idle"
  | "discovering"
  | "designing"
  | "indexing"
  | "done"
  | "error";
  percent: number;
}

export async function getProgress(): Promise<IndexingProgressInfo> {
  const res = await fetch(`${INDEXING_BASE}/progress`);
  return jsonOrThrow<IndexingProgressInfo>(res);
}

// ── Stats ──────────────────────────────────────────────────────────

export interface GraphStats {
  table_count: number;
  product_area_count: number;
  domain_knowledge_count: number;
  edge_count: number;
}

export async function getGraphStats(): Promise<GraphStats> {
  const res = await fetch(`${INDEXING_BASE}/stats`);
  return jsonOrThrow<GraphStats>(res);
}
