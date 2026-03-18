/* ── Table Indexing API types ─────────────────────────────────────── */

// ── Discovery ──────────────────────────────────────────────────────

export interface DiscoverTablesRequest {
  schema_dir?: string | null;
  database?: string | null;
  source?: "local" | "glue";
  region?: string;
  profile?: string | null;
}

export interface TableColumnInfo {
  name: string;
  data_type: string;
  description: string;
  is_partition: boolean;
}

export interface TableInfo {
  name: string;
  database: string;
  description: string;
  column_count: number;
  columns: TableColumnInfo[];
  location: string;
  storage_format: string;
  partition_keys: string[];
  row_count: number | null;
  is_indexed: boolean;
  index_status: "not_indexed" | "indexed" | "outdated";
}

export interface DiscoverTablesResponse {
  total_tables: number;
  indexed_tables: number;
  not_indexed_tables: number;
  outdated_tables: number;
  tables: TableInfo[];
  errors: string[];
}

// ── Design Preview ─────────────────────────────────────────────────

export interface PreviewDesignRequest {
  table_name: string;
  schema_dir?: string | null;
  database?: string | null;
}

export interface DesignColumn {
  name: string;
  data_type: string;
  description: string;
  business_terms: string[];
  is_primary_key: boolean;
  is_foreign_key: boolean;
  column_type: string;
  foreign_key_ref: string;
}

export interface DesignRelationship {
  source_table: string;
  target_table: string;
  relationship_type: string;
  source_column: string;
  target_column: string;
  description: string;
}

export interface DesignCost {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_s: number;
}

export interface PreviewDesignResponse {
  table_name: string;
  database: string;
  table_description: string;
  ai_description: string;
  entity_name: string;
  domain: string;
  synonyms: string[];
  tags: string[];
  columns: DesignColumn[];
  relationships: DesignRelationship[];
  llm_cost: DesignCost;
}

// ── Indexing ───────────────────────────────────────────────────────

export interface IndexTablesRequest {
  table_names: string[];
  schema_dir?: string | null;
  database?: string | null;
  skip_existing?: boolean;
}

export interface IndexTablesResponse {
  status: string;
  tables_discovered: number;
  tables_designed: number;
  tables_indexed: number;
  tables_skipped: number;
  tables_failed: number;
  graph_stats: Record<string, number>;
  llm_cost: Record<string, unknown>;
  errors: string[];
}

// ── Full Pipeline ─────────────────────────────────────────────────

export interface RunPipelineRequest {
  schema_dir?: string | null;
  database?: string | null;
  source?: "local" | "glue";
  only_new?: boolean;
  skip_existing?: boolean;
  table_names?: string[] | null;
  region?: string;
  profile?: string | null;
}

export interface RunPipelineResponse {
  status: string;
  tables_discovered: number;
  tables_designed: number;
  tables_indexed: number;
  tables_skipped: number;
  tables_failed: number;
  graph_stats: Record<string, number>;
  llm_cost: Record<string, unknown>;
  designs: Record<string, unknown>[];
  errors: string[];
}

// ── Progress & Stats ──────────────────────────────────────────────

export interface IndexingProgress {
  total: number;
  completed: number;
  failed: number;
  current_table: string;
  status: "idle" | "discovering" | "designing" | "indexing" | "done" | "error";
  percent: number;
}

export interface GraphIndexingStats {
  table_count: number;
  product_area_count: number;
  domain_knowledge_count: number;
  edge_count: number;
}
