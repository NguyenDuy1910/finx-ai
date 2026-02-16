import { ChatThread, ChatMode } from "@/types";

const STORAGE_KEY = "finx-chat-threads";

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
  patch: Partial<Pick<ChatThread, "sessionId" | "title" | "updatedAt">>
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

/** Delete a thread by id. */
export function deleteThread(threadId: string) {
  const threads = loadThreads().filter((t) => t.id !== threadId);
  saveThreads(threads);
}

/** Delete all threads. */
export function clearAllThreads() {
  saveThreads([]);
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
