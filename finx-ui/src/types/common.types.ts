export type NavPage = "chat" | "explore" | "playground" | "admin";

export type AdminTab = "search" | "stats" | "index" | "feedback" | "graph-explorer";

export const ADMIN_TABS: AdminTab[] = [
  "search",
  "stats",
  "index",
  "feedback",
  "graph-explorer",
];

export type ChatMode = "agent";

export const CHAT_MODE_LABELS: Record<ChatMode, string> = {
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
