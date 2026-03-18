export type NavPage = "chat" | "explore" | "schema-pipeline" | "graph-explorer" | "knowledge";

export type AdminTab = "search" | "stats" | "index" | "feedback" | "graph-explorer" | "table-indexing" | "data-loading" | "knowledge" | "schema-pipeline";

export const ADMIN_TABS: AdminTab[] = [
  "search",
  "stats",
  "index",
  "feedback",
  "graph-explorer",
  "table-indexing",
  "data-loading",
  "knowledge",
  "schema-pipeline",
];

export type ChatMode = "agent" | "team" | "knowledge";

export const CHAT_MODE_LABELS: Record<ChatMode, string> = {
  agent: "Agent",
  team: "Team",
  knowledge: "Knowledge",
};

export const CHAT_MODE_DESCRIPTIONS: Record<ChatMode, string> = {
  agent: "Single agent for focused tasks like research or exploration",
  team: "Multi-agent team that coordinates schema discovery, SQL generation, and execution",
  knowledge: "Company knowledge assistant — answers from internal Confluence documents with source citations",
};

export type UserIntent =
  | "data_query"
  | "schema_exploration"
  | "relationship_discovery"
  | "knowledge_lookup"
  | "feedback"
  | "clarification"
  | "general";
