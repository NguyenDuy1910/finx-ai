"use client";

import { useState, useCallback } from "react";
import {
  Users,
  Check,
  X,
  Loader2,
  Bot,
  Zap,
  Eye,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Brain,
  Wrench,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";
import type { MemberRunData, ToolCallData, ReasoningData } from "@/types";

// ── Agent icon/color mapping ─────────────────────────────────
const AGENT_STYLES: Record<
  string,
  { icon: React.ReactNode; gradient: string; border: string; bg: string; accent: string; ring: string }
> = {
  knowledge: {
    icon: <Bot className="h-3 w-3" />,
    gradient: "from-violet-500 to-purple-600",
    border: "border-violet-500/20",
    bg: "bg-violet-500/5",
    accent: "text-violet-500",
    ring: "ring-violet-500/30",
  },
  sql_generator: {
    icon: <Zap className="h-3 w-3" />,
    gradient: "from-blue-500 to-cyan-500",
    border: "border-blue-500/20",
    bg: "bg-blue-500/5",
    accent: "text-blue-500",
    ring: "ring-blue-500/30",
  },
  validation: {
    icon: <Check className="h-3 w-3" />,
    gradient: "from-emerald-500 to-green-500",
    border: "border-emerald-500/20",
    bg: "bg-emerald-500/5",
    accent: "text-emerald-500",
    ring: "ring-emerald-500/30",
  },
  sql_executor: {
    icon: <Zap className="h-3 w-3" />,
    gradient: "from-amber-500 to-orange-500",
    border: "border-amber-500/20",
    bg: "bg-amber-500/5",
    accent: "text-amber-500",
    ring: "ring-amber-500/30",
  },
};

function getAgentStyle(name: string) {
  const lower = name.toLowerCase().replace(/[-\s]/g, "_");
  for (const [key, style] of Object.entries(AGENT_STYLES)) {
    if (lower.includes(key)) return style;
  }
  return {
    icon: <Bot className="h-3 w-3" />,
    gradient: "from-slate-500 to-gray-500",
    border: "border-slate-500/20",
    bg: "bg-slate-500/5",
    accent: "text-slate-500",
    ring: "ring-slate-500/30",
  };
}

function formatAgentName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Inline thinking block (compact for member) ───────────────
function MemberThinkingBlock({ reasoning }: { reasoning: ReasoningData }) {
  const [expanded, setExpanded] = useState(false);

  if (reasoning.isActive && !reasoning.content) {
    return (
      <div className="flex items-center gap-1.5 rounded-lg border border-amber-500/15 bg-amber-500/5 px-2.5 py-1.5">
        <Brain className="h-3 w-3 animate-pulse text-amber-500" />
        <span className="text-[11px] font-medium text-amber-600 dark:text-amber-400">
          Thinking…
        </span>
        <div className="flex items-center gap-0.5">
          <span className="h-0.5 w-0.5 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.3s]" />
          <span className="h-0.5 w-0.5 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.15s]" />
          <span className="h-0.5 w-0.5 animate-bounce rounded-full bg-amber-500/60" />
        </div>
      </div>
    );
  }

  if (!reasoning.content) return null;

  return (
    <div className="overflow-hidden rounded-lg border border-amber-500/15 bg-amber-500/5">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left transition-colors hover:bg-amber-500/10"
      >
        <Sparkles className="h-3 w-3 shrink-0 text-amber-500" />
        <span className="flex-1 text-[11px] text-amber-700 dark:text-amber-300">
          {reasoning.isActive ? (
            <span className="flex items-center gap-1">
              Thinking…
              <span className="inline-flex items-center gap-0.5">
                <span className="h-0.5 w-0.5 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.3s]" />
                <span className="h-0.5 w-0.5 animate-bounce rounded-full bg-amber-500/60 [animation-delay:-0.15s]" />
                <span className="h-0.5 w-0.5 animate-bounce rounded-full bg-amber-500/60" />
              </span>
            </span>
          ) : (
            "Thought process"
          )}
        </span>
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-amber-500/60" />
        ) : (
          <Eye className="h-2.5 w-2.5 shrink-0 text-amber-500/40" />
        )}
      </button>
      {expanded && (
        <div className="border-t border-amber-500/10 px-2.5 py-1.5">
          <div className="max-h-[150px] overflow-y-auto">
            <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-amber-800/70 dark:text-amber-200/60">
              {reasoning.content}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Inline tool call (compact for member) ────────────────────
function MemberToolCall({ toolCall }: { toolCall: ToolCallData }) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = toolCall.status === "running";
  const hasError = toolCall.status === "error";

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border",
        hasError
          ? "border-red-500/15 bg-red-500/5"
          : isRunning
            ? "border-blue-500/15 bg-blue-500/5"
            : "border-emerald-500/15 bg-emerald-500/5"
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left transition-colors hover:bg-black/5 dark:hover:bg-white/5"
      >
        {isRunning ? (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin text-blue-500" />
        ) : (
          <Wrench className={cn("h-3 w-3 shrink-0", hasError ? "text-red-500" : "text-emerald-500")} />
        )}
        <span className="flex-1 truncate text-[11px] font-medium text-foreground/80">
          {isRunning ? "Calling" : "Called"}{" "}
          <code className="rounded bg-black/5 px-1 py-0.5 font-mono text-[10px] dark:bg-white/10">
            {toolCall.name}
          </code>
        </span>
        {toolCall.status === "completed" && <Check className="h-2.5 w-2.5 text-emerald-500" />}
        {hasError && <X className="h-2.5 w-2.5 text-red-500" />}
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground/60" />
        ) : (
          <ChevronRight className="h-2.5 w-2.5 text-muted-foreground/40" />
        )}
      </button>
      {expanded && (
        <div className="space-y-0 border-t border-inherit">
          {toolCall.args && JSON.stringify(toolCall.args) !== "{}" && (
            <div className="border-b border-inherit px-2.5 py-1.5">
              <p className="mb-0.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                Args
              </p>
              <pre className="overflow-x-auto rounded bg-black/5 p-1.5 text-[10px] leading-relaxed text-foreground/70 dark:bg-white/5">
                <code>{JSON.stringify(toolCall.args, null, 2)}</code>
              </pre>
            </div>
          )}
          {toolCall.result && (
            <div className="px-2.5 py-1.5">
              <p className="mb-0.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                {hasError ? "Error" : "Result"}
              </p>
              <pre
                className={cn(
                  "max-h-[120px] overflow-auto rounded p-1.5 text-[10px] leading-relaxed",
                  hasError
                    ? "bg-red-500/10 text-red-700 dark:text-red-300"
                    : "bg-black/5 text-foreground/70 dark:bg-white/5"
                )}
              >
                <code>{toolCall.result}</code>
              </pre>
            </div>
          )}
          {isRunning && !toolCall.result && (
            <div className="flex items-center gap-1.5 px-2.5 py-1.5">
              <Loader2 className="h-2.5 w-2.5 animate-spin text-blue-500" />
              <span className="text-[10px] text-muted-foreground">Executing…</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Expanded member card (shows output inline) ───────────────
interface MemberCardProps {
  member: MemberRunData;
  isLast: boolean;
  onMemberClick?: (member: MemberRunData) => void;
}

function MemberCard({ member, isLast, onMemberClick }: MemberCardProps) {
  const style = getAgentStyle(member.name);
  const isRunning = member.status === "running";
  const hasError = member.status === "error";
  const isDone = member.status === "completed";

  const [contentExpanded, setContentExpanded] = useState(true);

  const hasContent = !!member.content;
  const hasToolCalls = !!(member.toolCalls && member.toolCalls.length > 0);
  const hasReasoning = !!(member.reasoning && (member.reasoning.content || member.reasoning.isActive));
  const hasOutput = hasContent || hasToolCalls || hasReasoning || isRunning;

  return (
    <div className="relative animate-fade-in">
      {/* Timeline connector line */}
      {!isLast && (
        <div
          className={cn(
            "absolute bottom-0 left-[11px] top-[22px] w-[2px] transition-colors duration-500",
            isDone
              ? "bg-gradient-to-b from-emerald-500/30 to-emerald-500/10"
              : isRunning
                ? "bg-gradient-to-b from-primary/30 to-primary/10"
                : "bg-gradient-to-b from-red-500/30 to-red-500/10"
          )}
        />
      )}

      {/* Agent header row */}
      <div className="relative flex items-start gap-2.5">
        {/* Timeline dot */}
        <div className="relative z-10 mt-0.5 flex shrink-0">
          <div
            className={cn(
              "flex h-[22px] w-[22px] items-center justify-center rounded-full transition-all duration-300",
              isRunning && "bg-primary/10 ring-2 ring-primary/30 animate-pulse-ring",
              isDone && "bg-emerald-500/10 ring-1 ring-emerald-500/20",
              hasError && "bg-red-500/10 ring-1 ring-red-500/20"
            )}
          >
            {isRunning ? (
              <Loader2 className="h-3 w-3 animate-spin text-primary" />
            ) : isDone ? (
              <Check className="h-2.5 w-2.5 text-emerald-500" />
            ) : (
              <X className="h-2.5 w-2.5 text-red-500" />
            )}
          </div>
        </div>

        {/* Agent info + collapsible content */}
        <div className="min-w-0 flex-1 pb-3">
          {/* Agent name header */}
          <button
            type="button"
            onClick={() => setContentExpanded((v) => !v)}
            className="flex w-full items-center gap-1.5 text-left group/agent"
          >
            <div
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-md bg-gradient-to-br text-white shadow-sm transition-transform group-hover/agent:scale-105",
                style.gradient
              )}
            >
              <span className="scale-[0.6]">{style.icon}</span>
            </div>
            <span className="truncate text-[11px] font-semibold text-foreground/80">
              {formatAgentName(member.name)}
            </span>
            {member.model && (
              <span className="rounded-full bg-muted/50 px-1.5 py-0.5 text-[9px] text-muted-foreground/50">
                {member.model}
              </span>
            )}
            {isDone && member.total_tokens ? (
              <span className="ml-auto shrink-0 rounded-full bg-emerald-500/5 px-1.5 py-0.5 text-[10px] tabular-nums text-emerald-600/60">
                {member.total_tokens.toLocaleString()} tok
              </span>
            ) : null}
            {isRunning && (
              <span className="ml-auto flex items-center gap-1">
                <span className="text-[10px] font-medium text-primary/60">working</span>
                <span className="flex items-center gap-0.5">
                  <span className="h-1 w-1 animate-bounce rounded-full bg-primary/50 [animation-delay:-0.3s]" />
                  <span className="h-1 w-1 animate-bounce rounded-full bg-primary/50 [animation-delay:-0.15s]" />
                  <span className="h-1 w-1 animate-bounce rounded-full bg-primary/50" />
                </span>
              </span>
            )}
            {hasOutput && (
              <span className="ml-1 text-muted-foreground/40 transition-transform">
                {contentExpanded ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
              </span>
            )}
          </button>

          {/* Expanded content area */}
          {contentExpanded && hasOutput && (
            <div className={cn(
              "mt-2 space-y-2 rounded-xl border p-3 shadow-sm transition-all animate-slide-down",
              style.border, style.bg,
              isRunning && "shadow-primary/5",
              isDone && "shadow-emerald-500/5",
            )}>
              {/* Reasoning / thinking */}
              {hasReasoning && member.reasoning && (
                <MemberThinkingBlock reasoning={member.reasoning} />
              )}

              {/* Tool calls */}
              {hasToolCalls && member.toolCalls && (
                <div className="space-y-1.5">
                  {member.toolCalls.map((tc) => (
                    <MemberToolCall key={tc.id} toolCall={tc} />
                  ))}
                </div>
              )}

              {/* Streaming content */}
              {hasContent && (
                <div className="text-[12px] leading-relaxed text-foreground/80">
                  <MarkdownContent content={member.content} />
                  {isRunning && (
                    <span
                      className="ml-0.5 inline-block h-3 w-1 animate-pulse rounded-sm bg-primary align-text-bottom"
                      aria-label="Streaming"
                    />
                  )}
                </div>
              )}

              {/* Running but no content yet */}
              {isRunning && !hasContent && !hasToolCalls && !hasReasoning && (
                <div className="flex items-center gap-2 py-1">
                  <Loader2 className={cn("h-3.5 w-3.5 animate-spin", style.accent)} />
                  <span className="text-[11px] text-muted-foreground">
                    Agent is working…
                  </span>
                </div>
              )}

              {/* Error block */}
              {hasError && member.error && (
                <div className="flex items-start gap-1.5 rounded-lg border border-red-500/15 bg-red-500/5 px-2.5 py-2">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                  <div>
                    <p className="text-[11px] font-medium text-red-600 dark:text-red-400">Error</p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-red-600/80 dark:text-red-400/80">
                      {member.error}
                    </p>
                  </div>
                </div>
              )}

              {/* View full detail link */}
              {isDone && hasContent && onMemberClick && (
                <button
                  type="button"
                  onClick={() => onMemberClick(member)}
                  className="flex items-center gap-1 rounded-full border border-primary/10 bg-primary/[0.03] px-2.5 py-1 text-[10px] font-medium text-primary/60 transition-all hover:border-primary/20 hover:bg-primary/5 hover:text-primary"
                >
                  <Eye className="h-2.5 w-2.5" />
                  View full output
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main delegation block (timeline) ─────────────────────────
interface AgentDelegationBlockProps {
  members: MemberRunData[];
  onMemberClick?: (member: MemberRunData) => void;
}

export function AgentDelegationBlock({ members, onMemberClick }: AgentDelegationBlockProps) {
  const handleClick = useCallback(
    (member: MemberRunData) => {
      if (onMemberClick) onMemberClick(member);
    },
    [onMemberClick]
  );

  if (!members.length) return null;

  const completedCount = members.filter((m) => m.status === "completed").length;
  const runningCount = members.filter((m) => m.status === "running").length;
  const errorCount = members.filter((m) => m.status === "error").length;
  const totalTokens = members.reduce((sum, m) => sum + (m.total_tokens || 0), 0);
  const allDone = runningCount === 0 && members.length > 0;

  return (
    <div className="space-y-2" role="list" aria-label="Agent team workflow">
      {/* Compact summary bar */}
      <div
        className={cn(
          "flex items-center gap-2.5 rounded-xl border px-3.5 py-2 shadow-sm transition-all",
          allDone
            ? "border-emerald-500/20 bg-gradient-to-r from-emerald-500/8 to-emerald-500/3"
            : "border-primary/20 bg-gradient-to-r from-primary/8 to-primary/3"
        )}
      >
        <div className={cn(
          "flex h-6 w-6 items-center justify-center rounded-lg transition-colors",
          allDone ? "bg-emerald-500/10" : "bg-primary/10"
        )}>
          <Users className={cn("h-3.5 w-3.5", allDone ? "text-emerald-500" : "text-primary/60")} />
        </div>
        <span className="flex-1 text-[11px] text-muted-foreground/70">
          <span className="font-semibold text-foreground/80">Team Workflow</span>
          <span className="mx-2 text-muted-foreground/20">|</span>
          {members.length} agent{members.length > 1 ? "s" : ""}
          {runningCount > 0 && (
            <>
              <span className="mx-1.5 text-muted-foreground/20">·</span>
              <span className="font-medium text-primary/80">{runningCount} running</span>
            </>
          )}
          {completedCount > 0 && (
            <>
              <span className="mx-1.5 text-muted-foreground/20">·</span>
              <span className="font-medium text-emerald-600/80">{completedCount} done</span>
            </>
          )}
          {errorCount > 0 && (
            <>
              <span className="mx-1.5 text-muted-foreground/20">·</span>
              <span className="font-medium text-red-500/80">{errorCount} error</span>
            </>
          )}
        </span>
        {totalTokens > 0 && (
          <span className="rounded-full bg-muted/50 px-2 py-0.5 text-[10px] tabular-nums text-muted-foreground/50">
            {totalTokens.toLocaleString()} tokens
          </span>
        )}
        {allDone && <Sparkles className="h-3.5 w-3.5 text-emerald-500/60" />}
        {runningCount > 0 && (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary/60" />
        )}
      </div>

      {/* Expanded member cards with inline output */}
      <div className="pl-1.5">
        {members.map((member, idx) => (
          <MemberCard
            key={member.id}
            member={member}
            isLast={idx === members.length - 1}
            onMemberClick={onMemberClick}
          />
        ))}
      </div>
    </div>
  );
}
