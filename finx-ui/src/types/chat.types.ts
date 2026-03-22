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

  // ── Artifact metadata ─────────────────────────────────────
  /** URI to the artifact file (image, pdf, xlsx, etc.) — relative to artifacts dir */
  artifactUri?: string;
  /** MIME type of the artifact, e.g. "image/png", "application/pdf" */
  mimeType?: string;
  /** Whether this citation represents a file artifact rather than text content */
  isArtifact?: boolean;
  /** High-level artifact category */
  artifactType?: "image" | "pdf" | "spreadsheet" | "document" | "file";

  // ── Parent Confluence page context ────────────────────────
  /** Confluence parent page ID (when source is an attachment) */
  parentContentId?: string;
  /** Title of the parent Confluence page that contains this file */
  parentTitle?: string;
  /** URL to the parent Confluence page */
  parentUrl?: string;
  /** Confluence space key */
  spaceKey?: string;

  // ── Source classification ─────────────────────────────────
  /** Raw content type from pipeline: "page" | "attachment" | "comment" etc. */
  contentSourceType?: string;
  /** Chunk kind from pipeline: "image_caption" | "attachment" | "section" etc. */
  chunkKind?: string;
}

// ── Rendering helpers ─────────────────────────────────────────────────────────

/** Determine the best rendering strategy for a citation */
export type ArtifactRenderMode = "inline-image" | "inline-pdf" | "table-preview" | "document-card" | "download-card" | "page-card";

/** Map MIME type to a file extension label */
export function mimeToExtLabel(mime?: string): string {
  if (!mime) return "FILE";
  const map: Record<string, string> = {
    "image/png": "PNG", "image/jpeg": "JPEG", "image/gif": "GIF",
    "image/webp": "WEBP", "image/svg+xml": "SVG",
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "application/vnd.ms-excel": "XLS",
    "text/csv": "CSV",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/msword": "DOC",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PPTX",
    "application/vnd.ms-powerpoint": "PPT",
  };
  return map[mime] || mime.split("/").pop()?.toUpperCase() || "FILE";
}

/** Decision tree: how should this citation be rendered? */
export function getArtifactRenderMode(citation: CitationData): ArtifactRenderMode {
  if (!citation.isArtifact) return "page-card";
  if (citation.artifactType === "image") return "inline-image";
  if (citation.artifactType === "pdf") return "inline-pdf";
  if (citation.artifactType === "spreadsheet") return "table-preview";
  if (citation.artifactType === "document") return "document-card";
  return "download-card";
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
