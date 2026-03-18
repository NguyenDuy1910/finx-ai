export interface ColumnSchema {
  name: string;
  data_type: string;
  description?: string;
  is_partition?: boolean;
  is_primary_key?: boolean;
  is_foreign_key?: boolean;
  sample_values?: string[];
}

export interface TableSchema {
  name: string;
  database: string;
  columns: ColumnSchema[];
  description?: string;
  location?: string;
  storage_format?: string;
  partition_keys?: string[];
  row_count?: number | null;
}

export interface EnrichedColumn {
  name: string;
  data_type: string;
  description: string;
  is_partition: boolean;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  sample_values: string[];
  ai_description: string;
  business_terms: string[];
  column_type: string;
  foreign_key_ref: string;
}

export interface Relationship {
  source_table: string;
  target_table: string;
  relationship_type: string;
  source_column: string;
  target_column: string;
  description: string;
}

export interface LLMCost {
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  llm_calls: number;
  embedding_calls: number;
  cost_usd: number;
  duration_s: number;
  breakdown: Record<string, ModelCostBreakdown>;
}

export interface ModelCostBreakdown {
  input_tokens: number;
  output_tokens: number;
  calls: number;
  cost_usd: number;
}

export interface PreviewRequest {
  table_schema: TableSchema;
  context_tables?: string[];
}

export interface PreviewResponse {
  name: string;
  database: string;
  description: string;
  ai_description: string;
  entity_name: string;
  domain: string;
  synonyms: string[];
  tags: string[];
  enriched_columns: EnrichedColumn[];
  relationships: Relationship[];
  llm_cost: LLMCost;
}

export interface IndexRequest {
  tables: TableSchema[];
}

export interface IndexResponse {
  status: string;
  tables_indexed: number;
  tables_failed: number;
  graph_stats: Record<string, number>;
  errors: string[];
  llm_cost: LLMCost;
}

export interface SyncRequest {
  tables: TableSchema[];
}

export interface SyncResponse {
  status: string;
  tables_indexed: number;
  tables_failed: number;
  graph_stats: Record<string, number>;
  errors: string[];
}

export interface IndexingProgress {
  total: number;
  completed: number;
  failed: number;
  current_table: string;
  status: string;
  percent: number;
}

export interface GraphIndexingStats {
  table_count: number;
  product_area_count: number;
  domain_knowledge_count: number;
  edge_count: number;
}

export interface GlueTablesRequest {
  database: string;
  region?: string;
  accessKeyId?: string;
  secretAccessKey?: string;
  /** Named AWS profile from ~/.aws/credentials (e.g. "default") */
  profile?: string;
}

export interface GlueTablesResponse {
  tables: TableSchema[];
}

/* ── Usage Stats types ───────────────────────────────────────────── */

export interface UsageIndexRequest {
  query_logs: Array<{
    query_id?: string;
    user_id?: string;
    sql: string;
    execution_time_ms?: number;
    status?: string;
    timestamp?: string;
  }>;
}

export interface UsageIndexResponse {
  status: string;
  parsed_queries: number;
  tables_with_usage: number;
  graph_stats: Record<string, number>;
  errors: string[];
}

/* ── Example Query types ─────────────────────────────────────────── */

export interface ExampleQueryRequest {
  examples: Array<{
    sql: string;
    description?: string;
    tables_used?: string[];
    source?: string;
    author?: string;
    is_certified?: boolean;
    product_areas?: string[];
    tags?: string[];
  }>;
  skip_existing?: boolean;
}

export interface ExampleQueryResponse {
  status: string;
  loaded: number;
  skipped: number;
  errors: number;
}

/* ── Document Ingestion types ────────────────────────────────────── */

export interface IngestFilesResponse {
  status: string;
  chunks_produced: number;
  episodes_written: number;
  knowledge_sources_count: number;
  graph_stats: Record<string, number>;
  errors: string[];
}

export interface IngestUrlRequest {
  url: string;
  entity_name?: string;
  tags?: string[];
  write_to_graph?: boolean;
  confluence_base_url?: string;
  confluence_username?: string;
  confluence_api_token?: string;
}

export interface IngestUrlResponse {
  status: string;
  url: string;
  chunks_produced: number;
  episodes_written: number;
  knowledge_sources_count: number;
  graph_stats: Record<string, number>;
  errors: string[];
}

export interface IngestTextRequest {
  text: string;
  source_name?: string;
  entity_name?: string;
  tags?: string[];
  write_to_graph?: boolean;
}

export interface IngestTextResponse {
  status: string;
  chunks_produced: number;
  episodes_written: number;
  knowledge_sources_count: number;
  graph_stats: Record<string, number>;
  errors: string[];
}
