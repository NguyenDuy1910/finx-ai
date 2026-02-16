import type { ChatMode } from "./common.types";

export interface ChatRequest {
  message: string;
  database?: string;
  conversation_history: ConversationMessage[];
  available_databases: string[];
}

export interface ConversationMessage {
  role: string;
  content: string;
}

export interface ChatResponse {
  intent: string;
  response: string;
  sql?: string;
  database?: string;
  tables_used: string[];
  context_used: Record<string, unknown>;
  episode_id?: string;
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  needs_clarification: boolean;
  clarification_question?: string;
  suggestions: string[];
  session_id?: string;
}

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

export interface ChatThread {
  id: string;
  sessionId: string | null;
  title: string;
  mode: ChatMode;
  createdAt: number;
  updatedAt: number;
}
