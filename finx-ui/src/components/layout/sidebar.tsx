"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageSquarePlus, Trash2, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  loadThreads,
  deleteThread,
  clearAllThreads,
} from "@/lib/chat-store";
import type { ChatThread } from "@/types";

interface SidebarProps {
  activeThreadId: string | null;
  onSelectThread: (thread: ChatThread) => void;
  onNewChat: () => void;
  /** Incremented externally whenever threads are mutated (e.g. title update) */
  refreshKey?: number;
}

export function Sidebar({
  activeThreadId,
  onSelectThread,
  onNewChat,
  refreshKey,
}: SidebarProps) {
  const [threads, setThreads] = useState<ChatThread[]>([]);

  // Reload from localStorage whenever refreshKey changes
  useEffect(() => {
    setThreads(loadThreads());
  }, [refreshKey]);

  const handleDelete = useCallback(
    (e: React.MouseEvent, threadId: string) => {
      e.stopPropagation();
      deleteThread(threadId);
      setThreads(loadThreads());
      // If the deleted thread was active, create a new one
      if (threadId === activeThreadId) {
        onNewChat();
      }
    },
    [activeThreadId, onNewChat]
  );

  const handleClearAll = useCallback(() => {
    clearAllThreads();
    setThreads([]);
    onNewChat();
  }, [onNewChat]);

  // All threads (agent-only now)
  const filtered = threads;

  // Group threads: Today / Yesterday / Previous 7 Days / Older
  const groups = groupByDate(filtered);

  return (
    <aside className="flex h-full w-[var(--sidebar-width,280px)] flex-col border-r border-border/60 bg-background lg:bg-muted/20">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/40 px-4 py-3">
        <span className="text-[11px] font-semibold text-muted-foreground/70 uppercase tracking-widest">
          History
        </span>
        <button
          type="button"
          onClick={onNewChat}
          className="rounded-lg p-1.5 text-muted-foreground transition-all hover:bg-accent hover:text-foreground active:scale-90"
          title="New Chat"
          aria-label="New Chat"
        >
          <MessageSquarePlus className="h-4 w-4" />
        </button>
      </div>

      {/* Thread list */}
      <nav className="flex-1 overflow-y-auto px-2 py-2" aria-label="Chat threads">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-2 py-12 text-center">
            <MessageCircle className="h-8 w-8 text-muted-foreground/20" />
            <p className="text-xs text-muted-foreground/50">
              No conversations yet
            </p>
          </div>
        ) : (
          groups.map(([label, items]) => (
            <div key={label} className="mb-3">
              <p className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                {label}
              </p>
              <div className="space-y-0.5">
                {items.map((thread) => (
                  <button
                    key={thread.id}
                    type="button"
                    onClick={() => onSelectThread(thread)}
                    className={cn(
                      "group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-all duration-150",
                      thread.id === activeThreadId
                        ? "bg-primary/8 text-foreground font-medium"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                    )}
                    aria-current={thread.id === activeThreadId ? "true" : undefined}
                  >
                    <MessageCircle className={cn(
                      "h-3.5 w-3.5 shrink-0 transition-colors",
                      thread.id === activeThreadId
                        ? "text-primary/60"
                        : "opacity-40"
                    )} />
                    <span className="flex-1 truncate">{thread.title}</span>
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => handleDelete(e, thread.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleDelete(e as unknown as React.MouseEvent, thread.id);
                      }}
                      className="hidden shrink-0 rounded-md p-1 text-muted-foreground/40 transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:block"
                      title="Delete"
                      aria-label={`Delete ${thread.title}`}
                    >
                      <Trash2 className="h-3 w-3" />
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </nav>

      {/* Footer */}
      {filtered.length > 0 && (
        <div className="border-t border-border/40 px-3 py-2.5">
          <button
            type="button"
            onClick={handleClearAll}
            className="w-full rounded-lg px-2 py-1.5 text-xs text-muted-foreground/60 transition-all hover:bg-destructive/8 hover:text-destructive"
          >
            Clear all conversations
          </button>
        </div>
      )}
    </aside>
  );
}

// ── Helpers ──────────────────────────────────────────────────────

function groupByDate(threads: ChatThread[]): [string, ChatThread[]][] {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86_400_000;
  const weekStart = todayStart - 7 * 86_400_000;

  const groups: Record<string, ChatThread[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    Older: [],
  };

  for (const t of threads) {
    if (t.updatedAt >= todayStart) groups["Today"].push(t);
    else if (t.updatedAt >= yesterdayStart) groups["Yesterday"].push(t);
    else if (t.updatedAt >= weekStart) groups["Previous 7 Days"].push(t);
    else groups["Older"].push(t);
  }

  return Object.entries(groups).filter(([, items]) => items.length > 0);
}
