import type { ChatThread, ChatMode, CitationData, ToolCallData, ReasoningData, MemberRunData, RunMetrics, ActivityData } from "@/types";

const STORAGE_KEY = "finx-chat-threads";
const MSG_CACHE_PREFIX = "finx-chat-msgs-";

// ── Message history cache ─────────────────────────────────────────────────────

/** Serializable shape for a single cached message (matches renderMessages in chat-container). */
export interface CachedMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoning?: ReasoningData;
  toolCalls?: ToolCallData[];
  memberRuns?: MemberRunData[];
  runMetrics?: RunMetrics;
  citations?: CitationData[];
  activity?: ActivityData;
}

/** Save rendered messages for a thread. Overwrites any prior cache for this thread. */
export function saveMessageCache(threadId: string, messages: CachedMessage[]): void {
  if (typeof window === "undefined" || !messages.length) return;
  try {
    // Strip streaming-only fields and large content blobs to stay within storage limits.
    // Keep last 100 messages max to bound size.
    const trimmed = messages.slice(-100).map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      reasoning: m.reasoning ? { id: m.reasoning.id, content: m.reasoning.content, isActive: false } : undefined,
      toolCalls: m.toolCalls,
      memberRuns: m.memberRuns?.map((mr) => ({ ...mr, status: mr.status === "running" ? "completed" as const : mr.status })),
      runMetrics: m.runMetrics,
      citations: m.citations,
      // Drop activity — it's ephemeral
    }));
    localStorage.setItem(MSG_CACHE_PREFIX + threadId, JSON.stringify(trimmed));
  } catch {
    // localStorage full or serialization error — silently skip
  }
}

/** Load cached messages for a thread. Returns empty array if none. */
export function loadMessageCache(threadId: string): CachedMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(MSG_CACHE_PREFIX + threadId);
    if (!raw) return [];
    return JSON.parse(raw) as CachedMessage[];
  } catch {
    return [];
  }
}

/** Delete the message cache for a thread. */
export function deleteMessageCache(threadId: string): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(MSG_CACHE_PREFIX + threadId);
}

/** Delete all message caches (used when clearing all conversations). */
export function clearAllMessageCaches(): void {
  if (typeof window === "undefined") return;
  const keysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(MSG_CACHE_PREFIX)) keysToRemove.push(key);
  }
  keysToRemove.forEach((k) => localStorage.removeItem(k));
}

/** Read all threads from localStorage, newest first. */
export function loadThreads(): ChatThread[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const threads: ChatThread[] = JSON.parse(raw);
    return threads.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

/** Persist the full list to localStorage. */
function saveThreads(threads: ChatThread[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
}

/** Create a new thread and persist it. Returns the new thread. */
export function createThread(mode: ChatMode): ChatThread {
  const now = Date.now();
  const thread: ChatThread = {
    id: crypto.randomUUID(),
    sessionId: null,
    title: "New Chat",
    mode,
    createdAt: now,
    updatedAt: now,
  };
  const threads = loadThreads();
  threads.unshift(thread);
  saveThreads(threads);
  return thread;
}

/** Update a thread (e.g. set title or sessionId after first response). */
export function updateThread(
  threadId: string,
  patch: Partial<Pick<ChatThread, "sessionId" | "title" | "updatedAt" | "mode">>
) {
  const threads = loadThreads();
  const idx = threads.findIndex((t) => t.id === threadId);
  if (idx === -1) return;
  threads[idx] = {
    ...threads[idx],
    ...patch,
    updatedAt: patch.updatedAt ?? Date.now(),
  };
  saveThreads(threads);
}

/** Delete a thread by id, including its cached messages. */
export function deleteThread(threadId: string) {
  const threads = loadThreads().filter((t) => t.id !== threadId);
  saveThreads(threads);
  deleteMessageCache(threadId);
}

/** Delete all threads and their cached messages. */
export function clearAllThreads() {
  saveThreads([]);
  clearAllMessageCaches();
}

/**
 * Derive a short title from the first user message.
 * Truncates to ~50 chars and appends "…" if needed.
 */
export function titleFromMessage(message: string): string {
  const cleaned = message.replace(/\n/g, " ").trim();
  if (cleaned.length <= 50) return cleaned;
  return cleaned.slice(0, 47) + "…";
}
