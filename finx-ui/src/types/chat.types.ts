import type { ChatMode } from "./common.types";

export interface AgentChatRequest {
  message: string;
  session_id?: string;
  user_id?: string;
  stream?: boolean;
}

export interface AgentChatResponse {
  message: string;
  session_id?: string;
}

export interface ToolCallData {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string;
  error?: boolean;
  status: "running" | "completed" | "error";
}

export interface ReasoningData {
  id: string;
  content: string;
  isActive: boolean;
}

export interface RunMetrics {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  time_to_first_token?: number;
  reasoning_tokens?: number;
}

export interface MemberRunData {
  id: string;
  name: string;
  model?: string;
  status: "running" | "completed" | "error";
  content: string;
  error?: string;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  toolCalls?: ToolCallData[];
  reasoning?: ReasoningData;
}

export interface CitationData {
  id: string;
  title: string;
  sourceType: "confluence" | "qdrant" | "mcp" | "unknown";
  snippet: string;
  /** Full document content for rendering in the source panel */
  content?: string;
  page?: number | string;
  url?: string;
  score?: number;
  /** 1-based index matching [N] inline citation markers produced by the LLM */
  index?: number;
}

export interface ActivityData {
  status: "idle" | "searching" | "reading" | "reranking" | "drafting" | "done";
  query?: string;
  count?: number;
  timestamp: number;
}

export interface ChatThread {
  id: string;
  sessionId: string | null;
  title: string;
  mode: ChatMode;
  createdAt: number;
  updatedAt: number;
}
