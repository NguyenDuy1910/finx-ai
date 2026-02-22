export type NodeLabel =
  | "Table"
  | "Column"
  | "Domain"
  | "BusinessEntity"
  | "BusinessRule"
  | "CodeSet"
  | "QueryPattern";

export type EdgeType =
  | "HAS_COLUMN"
  | "JOIN"
  | "ENTITY_MAPPING"
  | "QUERY_USES_TABLE"
  | "SYNONYM"
  | "FOREIGN_KEY"
  | "BELONGS_TO_DOMAIN"
  | "CONTAINS_ENTITY"
  | "HAS_RULE"
  | "APPLIES_TO"
  | "COLUMN_MAPPING"
  | "HAS_CODESET"
  | "DERIVED_FROM";

export const NODE_LABELS: NodeLabel[] = [
  "Domain",
  "Table",
  "Column",
  "BusinessEntity",
  "BusinessRule",
  "CodeSet",
  "QueryPattern",
];

export const EDGE_TYPES: EdgeType[] = [
  "HAS_COLUMN",
  "JOIN",
  "ENTITY_MAPPING",
  "QUERY_USES_TABLE",
  "SYNONYM",
  "FOREIGN_KEY",
  "BELONGS_TO_DOMAIN",
  "CONTAINS_ENTITY",
  "HAS_RULE",
  "APPLIES_TO",
  "COLUMN_MAPPING",
  "HAS_CODESET",
  "DERIVED_FROM",
];

export const NODE_COLORS: Record<NodeLabel, string> = {
  Domain: "#8B5CF6",
  Table: "#3B82F6",
  Column: "#10B981",
  BusinessEntity: "#F59E0B",
  BusinessRule: "#EF4444",
  CodeSet: "#EAB308",
  QueryPattern: "#06B6D4",
};

export interface GraphNode {
  uuid: string;
  name: string;
  label: NodeLabel;
  summary: string;
  attributes: Record<string, unknown>;
  created_at?: string;
}

export interface GraphEdge {
  uuid: string;
  edge_type: EdgeType;
  source_node: GraphNode;
  target_node: GraphNode;
  fact: string;
  attributes: Record<string, unknown>;
}

export interface GraphNodeListResponse {
  nodes: GraphNode[];
  total: number;
  offset: number;
  limit: number;
}

export interface GraphEdgeListResponse {
  edges: GraphEdge[];
  total: number;
  offset: number;
  limit: number;
}

export interface CreateNodeRequest {
  label: string;
  name: string;
  description?: string;
  attributes?: Record<string, unknown>;
}

export interface UpdateNodeRequest {
  name?: string;
  description?: string;
  attributes?: Record<string, unknown>;
}

export interface CreateEdgeRequest {
  source_uuid: string;
  target_uuid: string;
  edge_type: string;
  fact?: string;
  attributes?: Record<string, unknown>;
}

export interface UpdateEdgeRequest {
  fact?: string;
  attributes?: Record<string, unknown>;
}

export interface ExploreNodeResponse {
  center: GraphNode;
  neighbors: GraphNode[];
  edges: GraphEdge[];
}

export interface LineageResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  paths: string[][];
}

export interface GraphOverviewDomain {
  uuid: string;
  name: string;
  table_count: number;
  entity_count: number;
}

export interface GraphOverviewResponse {
  domains: GraphOverviewDomain[];
  stats: Record<string, number>;
}

export interface GraphSearchResponse {
  nodes: GraphNode[];
  total: number;
}
