"use client";

import { useState, memo } from "react";
import { Brain, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface ThinkingBlockProps {
  content: string;
  isActive: boolean;
}

export const ThinkingBlock = memo(function ThinkingBlock({ content, isActive }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  if (isActive && !content) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/8 px-3 py-2 animate-fade-in">
        <Brain className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 animate-pulse" />
        <span className="text-[0.8125rem] font-medium text-amber-700 dark:text-amber-300">
          Reasoning…
        </span>
        <div className="flex items-center gap-0.5">
          <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/50 [animation-delay:-0.3s]" />
          <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/50 [animation-delay:-0.15s]" />
          <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/50" />
        </div>
      </div>
    );
  }

  if (!content) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-amber-500/20 bg-gradient-to-r from-amber-500/8 to-amber-500/3 shadow-sm shadow-amber-500/5">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-amber-100/50 dark:hover:bg-amber-500/10"
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse reasoning" : "Expand reasoning"}
      >
        <Brain className="h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
        <span className="flex-1 text-[0.8125rem] text-amber-800 dark:text-amber-200">
          {isActive ? (
            <span className="flex items-center gap-1.5">
              Reasoning…
              <span className="inline-flex items-center gap-0.5">
                <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/50 [animation-delay:-0.3s]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/50 [animation-delay:-0.15s]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-amber-500/50" />
              </span>
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              Thought process
              <span className="text-[0.6875rem] text-amber-600/40 dark:text-amber-400/30">
                ({content.length.toLocaleString()} chars)
              </span>
            </span>
          )}
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-amber-500/50 transition-transform duration-200",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded && content && (
        <div className="animate-fade-in border-t border-amber-200/60 dark:border-amber-500/10 px-3 py-2.5">
          <div className="max-h-[240px] overflow-y-auto pr-1">
            <p className="whitespace-pre-wrap text-[0.8125rem] leading-relaxed text-amber-900/60 dark:text-amber-200/50">
              {content}
            </p>
          </div>
        </div>
      )}
    </div>
  );
});
