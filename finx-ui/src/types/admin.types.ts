export interface StatsResponse {
  entities: Record<string, number>;
  episodes: Record<string, number>;
}

export interface IndexSchemaRequest {
  schema_path: string;
  database?: string;
  skip_existing: boolean;
}

export interface IndexSchemaResponse {
  tables: number;
  columns: number;
  entities: number;
  edges: number;
  domains: number;
  skipped: number;
}

export interface FeedbackRequest {
  natural_language: string;
  generated_sql: string;
  feedback: string;
  rating?: number;
  corrected_sql: string;
}

export interface FeedbackResponse {
  episode_id: string;
  status: string;
}
