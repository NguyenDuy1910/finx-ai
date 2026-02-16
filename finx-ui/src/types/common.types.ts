export type NavPage = "chat" | "explore" | "playground" | "admin";

export type ChatMode = "sql" | "agent";

export const CHAT_MODE_LABELS: Record<ChatMode, string> = {
  sql: "SQL Assistant",
  agent: "Knowledge Agent",
};

export type UserIntent =
  | "data_query"
  | "schema_exploration"
  | "relationship_discovery"
  | "knowledge_lookup"
  | "feedback"
  | "clarification"
  | "general";
