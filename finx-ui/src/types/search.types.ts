export interface SearchRequest {
  query: string;
  database?: string;
  top_k: number;
  threshold?: number;
  entities?: string[];
  intent?: string;
  domain?: string;
  business_terms?: string[];
  column_hints?: string[];
  include_patterns?: boolean;
  include_context?: boolean;
}

export interface SearchResultItem {
  name: string;
  label: string;
  summary: string;
  score: number;
  attributes: Record<string, unknown>;
}

export interface TableContextResponse {
  table: string;
  database: string;
  description: string;
  partition_keys: string[];
  columns: Record<string, unknown>[];
  entities: Record<string, unknown>[];
  related_tables: Record<string, unknown>[];
}

export interface SchemaSearchResponse {
  tables: SearchResultItem[];
  columns: SearchResultItem[];
  entities: SearchResultItem[];
  patterns: Record<string, unknown>[];
  context: TableContextResponse[];
  ranked_results: Record<string, unknown>[];
  query_analysis?: Record<string, unknown>;
  search_metadata: Record<string, unknown>;
}

export interface TableDetailResponse {
  table: Record<string, unknown> | null;
  columns: Record<string, unknown>[];
  edges: Record<string, unknown>[];
}

export interface RelatedTablesResponse {
  table: string;
  relations: Record<string, unknown>[];
}

export interface JoinPathResponse {
  source: string;
  target: string;
  direct_joins: Record<string, unknown>[];
  shared_intermediates: string[];
}

export interface TableResponse {
  uuid: string;
  name: string;
  database: string;
  description: string;
  partition_keys: string[];
  row_count?: number;
  storage_format: string;
  location: string;
}

export interface Text2SQLRequest {
  query: string;
  database?: string;
  conversation_history: { role: string; content: string }[];
}

export interface Text2SQLResponse {
  query: string;
  sql: string;
  database: string;
  tables_used: string[];
  reasoning: string;
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  episode_id?: string;
}

export interface HealthResponse {
  status: string;
  graph_connected: boolean;
  version: string;
}
