"use client";

import { useState } from "react";
import { Brain, ChevronDown, Sparkles, Eye } from "lucide-react";

interface ThinkingBlockProps {
  content: string;
  isActive: boolean;
}

export function ThinkingBlock({ content, isActive }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  // While actively thinking, show animated indicator
  if (isActive && !content) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-gradient-to-r from-amber-500/8 to-amber-500/3 px-3 py-2.5 shadow-sm shadow-amber-500/5 animate-fade-in">
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

  const charCount = content.length;

  return (
    <div className="overflow-hidden rounded-xl border border-amber-500/20 bg-gradient-to-r from-amber-500/8 to-amber-500/3 shadow-sm shadow-amber-500/5">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-amber-500/10"
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse thinking" : "Expand thinking"}
      >
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-amber-500" />
        <span className="flex-1 text-xs text-amber-700 dark:text-amber-300">
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
            <span className="flex items-center gap-1.5">
              Thought for a moment
              <span className="text-[10px] text-amber-600/40 dark:text-amber-400/40">
                ({charCount.toLocaleString()} chars)
              </span>
            </span>
          )}
        </span>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-amber-500/60 transition-transform" />
        ) : (
          <Eye className="h-3 w-3 shrink-0 text-amber-500/40" />
        )}
      </button>

      {expanded && content && (
        <div className="animate-fade-in border-t border-amber-500/10 px-3 py-2">
          <div className="max-h-[200px] overflow-y-auto">
            <p className="whitespace-pre-wrap text-xs leading-relaxed text-amber-800/70 dark:text-amber-200/60">
              {content}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
