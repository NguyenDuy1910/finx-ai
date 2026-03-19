"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageSquarePlus, Trash2, MessageCircle, Bot, Users, BookOpen } from "lucide-react";
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
  refreshKey?: number;
}

const MODE_ICONS: Record<string, typeof Bot> = {
  agent: Bot,
  team: Users,
  knowledge: BookOpen,
};

const MODE_COLORS: Record<string, string> = {
  agent: "text-blue-500",
  team: "text-violet-500",
  knowledge: "text-emerald-500",
};

export function Sidebar({
  activeThreadId,
  onSelectThread,
  onNewChat,
  refreshKey,
}: SidebarProps) {
  const [threads, setThreads] = useState<ChatThread[]>([]);

  useEffect(() => {
    setThreads(loadThreads());
  }, [refreshKey]);

  const handleDelete = useCallback(
    (e: React.MouseEvent, threadId: string) => {
      e.stopPropagation();
      deleteThread(threadId);
      setThreads(loadThreads());
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

  const groups = groupByDate(threads);

  return (
    <aside className="flex h-full w-[var(--sidebar-width,256px)] flex-col bg-sidebar-bg border-r border-sidebar-border">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-sidebar-border">
        <span className="text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-muted-foreground/60">
          Conversations
        </span>
        <button
          type="button"
          onClick={onNewChat}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground transition-all hover:bg-sidebar-hover-bg hover:text-foreground active:scale-90"
          title="New Chat"
          aria-label="New Chat"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Thread list */}
      <nav className="flex-1 overflow-y-auto px-2 py-2.5" aria-label="Chat threads">
        {threads.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-4 py-14 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted/60">
              <MessageCircle className="h-5 w-5 text-muted-foreground/30" />
            </div>
            <div>
              <p className="text-[0.8125rem] font-medium text-muted-foreground/50">
                No conversations yet
              </p>
              <p className="mt-0.5 text-[0.75rem] text-muted-foreground/35">
                Start a new chat to begin
              </p>
            </div>
          </div>
        ) : (
          groups.map(([label, items]) => (
            <div key={label} className="mb-4">
              <p className="mb-1 px-2 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-muted-foreground/40">
                {label}
              </p>
              <div className="space-y-0.5">
                {items.map((thread) => {
                  const isActive = thread.id === activeThreadId;
                  const ModeIcon = MODE_ICONS[thread.mode ?? "agent"] ?? Bot;
                  const modeColor = MODE_COLORS[thread.mode ?? "agent"] ?? "text-muted-foreground/40";

                  return (
                    <div
                      key={thread.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => onSelectThread(thread)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelectThread(thread);
                        }
                      }}
                      className={cn(
                        "group relative flex w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[0.8125rem] transition-all duration-100 select-none",
                        isActive
                          ? "bg-sidebar-active-bg text-sidebar-active-text font-medium"
                          : "text-muted-foreground hover:bg-sidebar-hover-bg hover:text-foreground"
                      )}
                      aria-current={isActive ? "true" : undefined}
                    >
                      {isActive && (
                        <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary" />
                      )}
                      <ModeIcon className={cn("h-3.5 w-3.5 shrink-0 opacity-60", isActive ? "text-primary" : modeColor)} />
                      <span className="flex-1 truncate">{thread.title}</span>
                      <button
                        type="button"
                        onClick={(e) => handleDelete(e, thread.id)}
                        className="hidden shrink-0 rounded-md p-0.5 text-muted-foreground/30 transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:block"
                        title="Delete"
                        aria-label={`Delete ${thread.title}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </nav>

      {/* Footer */}
      {threads.length > 0 && (
        <div className="border-t border-sidebar-border px-3 py-2.5">
          <button
            type="button"
            onClick={handleClearAll}
            className="w-full rounded-lg px-2 py-1.5 text-[0.75rem] text-muted-foreground/50 transition-all hover:bg-destructive/8 hover:text-destructive"
          >
            Clear all conversations
          </button>
        </div>
      )}
    </aside>
  );
}

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
