/* ── Schema Pipeline types ─────────────────────────────────────────
 *  Full pipeline flow: Connect → Select → Enrich → Preview → Index → Review
 */

// ── Pipeline Steps ─────────────────────────────────────────────────

export type PipelineStep =
  | "connect"
  | "select"
  | "enrich"
  | "preview"
  | "index"
  | "review";

export const PIPELINE_STEPS: {
  key: PipelineStep;
  label: string;
  description: string;
}[] = [
    {
      key: "connect",
      label: "Connect",
      description: "Connect to database or schema source",
    },
    {
      key: "select",
      label: "Select Tables",
      description: "Browse and select tables to index",
    },
    {
      key: "enrich",
      label: "Enrich Metadata",
      description: "Add descriptions and business context",
    },
    {
      key: "preview",
      label: "AI Preview",
      description: "Review AI-generated graph design",
    },
    {
      key: "index",
      label: "Index",
      description: "Execute indexing into knowledge graph",
    },
    {
      key: "review",
      label: "Review",
      description: "Review results and statistics",
    },
  ];

// ── Connection ─────────────────────────────────────────────────────

export type ConnectionSource = "glue";

export interface ConnectionConfig {
  source: ConnectionSource;
  database?: string;
  region?: string;
  profile?: string;
}

// ── Table with user enrichment ─────────────────────────────────────

export interface PipelineColumnInfo {
  name: string;
  data_type: string;
  description: string;
  is_partition: boolean;
  /** User-provided custom description override */
  custom_description?: string;
  /** User-added business terms */
  custom_business_terms?: string[];
}

export interface PipelineTableInfo {
  name: string;
  database: string;
  description: string;
  column_count: number;
  columns: PipelineColumnInfo[];
  location: string;
  storage_format: string;
  partition_keys: string[];
  row_count: number | null;
  is_indexed: boolean;
  index_status: "not_indexed" | "indexed" | "outdated";

  /** ── User enrichment fields ── */
  custom_description?: string;
  custom_domain?: string;
  custom_tags?: string[];
  custom_synonyms?: string[];
  /** Any extra business context the user wants to provide */
  business_context?: string;
}

// ── Context documents ──────────────────────────────────────────────

export type ContextDocumentType = "file" | "url" | "text";

export interface ContextDocument {
  /** Client-side unique id */
  id: string;
  /** Display name (filename, URL, or "Custom text") */
  name: string;
  type: ContextDocumentType;
  /** Extracted plain text from the document */
  text: string;
  /** Approximate character count */
  charCount: number;
}

// ── Enrichment form data ───────────────────────────────────────────

export interface TableEnrichment {
  table_name: string;
  custom_description?: string;
  custom_domain?: string;
  custom_tags?: string[];
  custom_synonyms?: string[];
  business_context?: string;
  column_overrides?: Record<
    string,
    {
      custom_description?: string;
      custom_business_terms?: string[];
    }
  >;
  /** Context documents attached to this table for AI preview */
  context_documents?: ContextDocument[];
}

// ── Preview result (for each table) ────────────────────────────────

export interface PreviewColumnDesign {
  name: string;
  data_type: string;
  description: string;
  business_terms: string[];
  is_primary_key: boolean;
  is_foreign_key: boolean;
  column_type: string;
  foreign_key_ref: string;
}

export interface PreviewRelationship {
  source_table: string;
  target_table: string;
  relationship_type: string;
  source_column: string;
  target_column: string;
  description: string;
}

export interface PreviewCost {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_s: number;
}

// ── Knowledge Graph types ──────────────────────────────────────────

export interface KGNode {
  id: string;
  label: string;
  type: "table" | "column" | "domain" | "entity" | "concept" | string;
  description?: string;
}

export interface KGEdge {
  source: string;
  target: string;
  label: string;
  type: "structural" | "semantic" | "business" | string;
}

export interface TablePreviewResult {
  table_name: string;
  database: string;
  table_description: string;
  ai_description: string;
  entity_name: string;
  domain: string;
  synonyms: string[];
  tags: string[];
  columns: PreviewColumnDesign[];
  relationships: PreviewRelationship[];
  llm_cost: PreviewCost;
  status: "pending" | "loading" | "done" | "error";
  error?: string;
  /** Knowledge Graph nodes from the enricher agent */
  kg_nodes?: KGNode[];
  /** Knowledge Graph edges from the enricher agent */
  kg_edges?: KGEdge[];
}

// ── Indexing result ────────────────────────────────────────────────

export interface IndexingLLMCost {
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  llm_calls: number;
  embedding_calls: number;
  cost_usd: number;
  duration_s: number;
  breakdown: Record<string, {
    input_tokens: number;
    output_tokens: number;
    calls: number;
    cost_usd: number;
  }>;
}

export interface PipelineIndexResult {
  status: string;
  tables_indexed: number;
  tables_failed: number;
  graph_stats: Record<string, number>;
  errors: string[];
  llm_cost?: IndexingLLMCost;
}

// ── Pipeline state (full context) ──────────────────────────────────

export interface PipelineState {
  currentStep: PipelineStep;
  completedSteps: Set<PipelineStep>;
  connection: ConnectionConfig;
  discoveredTables: PipelineTableInfo[];
  selectedTableNames: Set<string>;
  enrichments: Record<string, TableEnrichment>;
  previews: Record<string, TablePreviewResult>;
  indexResult: PipelineIndexResult | null;
  isLoading: boolean;
  error: string | null;
}
