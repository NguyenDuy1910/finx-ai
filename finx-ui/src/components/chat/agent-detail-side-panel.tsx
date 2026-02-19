"use client";

import { useEffect, useRef } from "react";
import {
  X,
  Bot,
  Zap,
  Check,
  Copy,
  Loader2,
  AlertTriangle,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";
import { useClipboard } from "@/hooks/use-clipboard";
import type { MemberRunData } from "@/types";

// ── Agent style mapping (shared with delegation block) ───────
const AGENT_STYLES: Record<
  string,
  { icon: React.ReactNode; gradient: string; border: string; bg: string; accent: string }
> = {
  knowledge: {
    icon: <Bot className="h-4 w-4" />,
    gradient: "from-violet-500 to-purple-600",
    border: "border-violet-500/20",
    bg: "bg-violet-500/5",
    accent: "text-violet-500",
  },
  sql_generator: {
    icon: <Zap className="h-4 w-4" />,
    gradient: "from-blue-500 to-cyan-500",
    border: "border-blue-500/20",
    bg: "bg-blue-500/5",
    accent: "text-blue-500",
  },
  validation: {
    icon: <Check className="h-4 w-4" />,
    gradient: "from-emerald-500 to-green-500",
    border: "border-emerald-500/20",
    bg: "bg-emerald-500/5",
    accent: "text-emerald-500",
  },
  sql_executor: {
    icon: <Zap className="h-4 w-4" />,
    gradient: "from-amber-500 to-orange-500",
    border: "border-amber-500/20",
    bg: "bg-amber-500/5",
    accent: "text-amber-500",
  },
};

function getAgentStyle(name: string) {
  const lower = name.toLowerCase().replace(/[-\s]/g, "_");
  for (const [key, style] of Object.entries(AGENT_STYLES)) {
    if (lower.includes(key)) return style;
  }
  return {
    icon: <Bot className="h-4 w-4" />,
    gradient: "from-slate-500 to-gray-500",
    border: "border-slate-500/20",
    bg: "bg-slate-500/5",
    accent: "text-slate-500",
  };
}

function formatAgentName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Status badge ─────────────────────────────────────────────
function StatusBadge({ status }: { status: MemberRunData["status"] }) {
  switch (status) {
    case "running":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
          <Loader2 className="h-2.5 w-2.5 animate-spin" />
          Running
        </span>
      );
    case "completed":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
          <Sparkles className="h-2.5 w-2.5" />
          Completed
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-600 dark:text-red-400">
          <AlertTriangle className="h-2.5 w-2.5" />
          Error
        </span>
      );
    default:
      return null;
  }
}

interface AgentDetailSidePanelProps {
  member: MemberRunData;
  onClose: () => void;
}

export function AgentDetailSidePanel({ member, onClose }: AgentDetailSidePanelProps) {
  const style = getAgentStyle(member.name);
  const hasError = member.status === "error";
  const isRunning = member.status === "running";
  const { copied, copy } = useClipboard();
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Scroll to top when member changes
  useEffect(() => {
    panelRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [member.id]);

  const hasTokens = !!(member.input_tokens || member.output_tokens || member.total_tokens);

  return (
    <div
      className="animate-slide-in-right flex h-full flex-col border-l border-border/60 bg-background"
      role="complementary"
      aria-label={`${formatAgentName(member.name)} agent detail`}
    >
      {/* ── Header ────────────────────────────────────────── */}
      <div
        className={cn(
          "flex items-center gap-3 border-b px-4 py-3",
          style.bg
        )}
      >
        {/* Agent icon */}
        <div
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-white shadow-sm",
            style.gradient
          )}
        >
          {style.icon}
        </div>

        {/* Name + model */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground">
              {formatAgentName(member.name)}
            </h3>
            <StatusBadge status={member.status} />
          </div>
          {member.model && (
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground/60">
              Model: {member.model}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1">
          {member.content && (
            <button
              type="button"
              onClick={() => copy(member.content)}
              className={cn(
                "rounded-md p-1.5 transition-colors",
                copied
                  ? "text-emerald-500"
                  : "text-muted-foreground/50 hover:bg-accent hover:text-foreground"
              )}
              title={copied ? "Copied!" : "Copy output"}
              aria-label={copied ? "Copied to clipboard" : "Copy agent output"}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground/50 transition-colors hover:bg-accent hover:text-foreground"
            aria-label="Close panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ── Content ───────────────────────────────────────── */}
      <div ref={panelRef} className="flex-1 overflow-y-auto">
        {/* Main output */}
        <div className="px-4 py-4">
          {member.content ? (
            <div className="prose-sm min-w-0 overflow-hidden text-sm leading-relaxed text-foreground/85">
              <div className="break-words [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_code]:break-all [&_table]:w-full [&_img]:max-w-full [&_img]:h-auto">
                <MarkdownContent content={member.content} />
              </div>
            </div>
          ) : isRunning ? (
            <div className="flex flex-col items-center justify-center gap-3 py-12">
              <Loader2 className={cn("h-6 w-6 animate-spin", style.accent)} />
              <p className="text-xs text-muted-foreground">
                Agent is working…
              </p>
            </div>
          ) : (
            <p className="py-8 text-center text-xs italic text-muted-foreground/40">
              No output from this agent
            </p>
          )}
        </div>

        {/* Error block */}
        {hasError && member.error && (
          <div className="mx-4 mb-4 rounded-lg border border-red-500/15 bg-red-500/5 px-4 py-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-red-600 dark:text-red-400">
                  Error
                </p>
                <p className="mt-1 break-words text-xs leading-relaxed text-red-600/80 dark:text-red-400/80">
                  {member.error}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Token metrics footer ──────────────────────────── */}
      {hasTokens && (
        <div className="flex items-center gap-5 border-t border-border/40 bg-muted/5 px-4 py-2.5">
          {member.input_tokens ? (
            <div className="flex flex-col">
              <span className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/40">
                Input
              </span>
              <span className="text-xs tabular-nums font-medium text-foreground/60">
                {member.input_tokens.toLocaleString()}
              </span>
            </div>
          ) : null}
          {member.output_tokens ? (
            <div className="flex flex-col">
              <span className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/40">
                Output
              </span>
              <span className="text-xs tabular-nums font-medium text-foreground/60">
                {member.output_tokens.toLocaleString()}
              </span>
            </div>
          ) : null}
          {member.total_tokens ? (
            <div className="ml-auto flex flex-col items-end">
              <span className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/40">
                Total
              </span>
              <span className="text-xs tabular-nums font-semibold text-foreground/70">
                {member.total_tokens.toLocaleString()}
              </span>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
