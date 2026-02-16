"use client";

import { useState } from "react";
import { Brain, ChevronDown, ChevronRight, Sparkles } from "lucide-react";

interface ThinkingBlockProps {
  content: string;
  isActive: boolean;
}

export function ThinkingBlock({ content, isActive }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  // While actively thinking, show animated indicator
  if (isActive && !content) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 animate-fade-in">
        <Brain className="h-4 w-4 animate-pulse text-amber-500" />
        <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
          Thinking…
        </span>
        <div className="flex items-center gap-0.5">
          <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.3s]" />
          <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.15s]" />
          <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/60" />
        </div>
      </div>
    );
  }

  if (!content) return null;

  const lines = content.split("\n").filter(Boolean);
  const preview = lines[0]?.slice(0, 120) || "";
  const hasMore = content.length > 120;

  return (
    <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-amber-500/10 transition-colors"
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse thinking" : "Expand thinking"}
      >
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-amber-500" />
        <span className="flex-1 truncate text-xs text-amber-700 dark:text-amber-300">
          {isActive ? (
            <span className="flex items-center gap-1.5">
              Thinking…
              <span className="inline-flex items-center gap-0.5">
                <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.3s]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.15s]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/60" />
              </span>
            </span>
          ) : (
            <>Thought for a moment</>
          )}
        </span>
        {hasMore && (
          expanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-amber-500/60 transition-transform" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-amber-500/60 transition-transform" />
          )
        )}
      </button>

      {(expanded || !hasMore) && content && (
        <div className="border-t border-amber-500/10 px-3 py-2">
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-amber-800/70 dark:text-amber-200/60">
            {content}
          </p>
        </div>
      )}

      {!expanded && hasMore && (
        <div className="border-t border-amber-500/10 px-3 py-1.5">
          <p className="truncate text-[11px] text-amber-700/50 dark:text-amber-300/40">
            {preview}…
          </p>
        </div>
      )}
    </div>
  );
}
