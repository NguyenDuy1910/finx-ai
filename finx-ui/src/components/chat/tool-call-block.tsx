"use client";

import { useState } from "react";
import {
  Wrench,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolCallData } from "@/types";

interface ToolCallBlockProps {
  toolCall: ToolCallData;
}

export function ToolCallBlock({ toolCall }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const isRunning = toolCall.status === "running";
  const hasError = toolCall.status === "error";
  const isDone = toolCall.status === "completed";

  const statusColor = hasError
    ? "border-red-500/20 bg-red-500/5"
    : isRunning
      ? "border-blue-500/20 bg-blue-500/5"
      : "border-emerald-500/20 bg-emerald-500/5";

  const iconColor = hasError
    ? "text-red-500"
    : isRunning
      ? "text-blue-500"
      : "text-emerald-500";

  // Format args for display
  const argsStr = toolCall.args
    ? JSON.stringify(toolCall.args, null, 2)
    : null;

  // Truncate long results
  const resultPreview =
    toolCall.result && toolCall.result.length > 200
      ? toolCall.result.slice(0, 200) + "…"
      : toolCall.result;

  return (
    <div className={cn("rounded-xl border overflow-hidden", statusColor)}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-black/5 dark:hover:bg-white/5"
        aria-expanded={expanded}
        aria-label={`${isRunning ? "Running" : "Completed"} tool call: ${toolCall.name}`}
      >
        {isRunning ? (
          <Loader2 className={cn("h-3.5 w-3.5 shrink-0 animate-spin", iconColor)} />
        ) : (
          <Wrench className={cn("h-3.5 w-3.5 shrink-0", iconColor)} />
        )}

        <span className="flex-1 truncate text-xs font-medium text-foreground/80">
          {isRunning ? "Calling" : "Called"}{" "}
          <code className="rounded bg-black/5 px-1 py-0.5 font-mono text-[11px] dark:bg-white/10">
            {toolCall.name}
          </code>
        </span>

        <div className="flex items-center gap-1.5">
          {isDone && <Check className="h-3 w-3 text-emerald-500" />}
          {hasError && <X className="h-3 w-3 text-red-500" />}
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground/60 transition-transform" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60 transition-transform" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="space-y-0 border-t border-inherit animate-fade-in">
          {/* Arguments */}
          {argsStr && argsStr !== "{}" && (
            <div className="border-b border-inherit px-3 py-2">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                Arguments
              </p>
              <pre className="overflow-x-auto rounded bg-black/5 p-2 text-[11px] leading-relaxed text-foreground/70 dark:bg-white/5">
                <code>{argsStr}</code>
              </pre>
            </div>
          )}

          {/* Result */}
          {toolCall.result && (
            <div className="px-3 py-2">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                {hasError ? "Error" : "Result"}
              </p>
              <pre
                className={cn(
                  "overflow-x-auto rounded p-2 text-[11px] leading-relaxed",
                  hasError
                    ? "bg-red-500/10 text-red-700 dark:text-red-300"
                    : "bg-black/5 text-foreground/70 dark:bg-white/5"
                )}
              >
                <code>{expanded ? toolCall.result : resultPreview}</code>
              </pre>
            </div>
          )}

          {/* Loading state */}
          {isRunning && !toolCall.result && (
            <div className="flex items-center gap-2 px-3 py-2">
              <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
              <span className="text-[11px] text-muted-foreground">
                Executing…
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Renders a list of tool calls compactly */
export function ToolCallList({ toolCalls }: { toolCalls: ToolCallData[] }) {
  if (!toolCalls.length) return null;

  return (
    <div className="space-y-1.5" role="list" aria-label="Tool calls">
      {toolCalls.map((tc) => (
        <ToolCallBlock key={tc.id} toolCall={tc} />
      ))}
    </div>
  );
}
