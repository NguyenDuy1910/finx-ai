"use client";

import { useState, memo } from "react";
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
  AlertTriangle,
  Clock,
  Search,
  BarChart3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";
import type { MemberRunData } from "@/types";

// ── Agent icon/color mapping ─────────────────────────────────
const AGENT_STYLES: Record<
  string,
  { icon: React.ReactNode; gradient: string; border: string; bg: string; accent: string; ring: string; label: string; description: string }
> = {
  knowledge: {
    icon: <Search className="h-3 w-3" />,
    gradient: "from-violet-500 to-purple-600",
    border: "border-violet-500/15",
    bg: "bg-violet-500/[0.03]",
    accent: "text-violet-500",
    ring: "ring-violet-500/30",
    label: "Knowledge Discovery",
    description: "Searching schema & business rules",
  },
  sql_generator: {
    icon: <Zap className="h-3 w-3" />,
    gradient: "from-blue-500 to-cyan-500",
    border: "border-blue-500/15",
    bg: "bg-blue-500/[0.03]",
    accent: "text-blue-500",
    ring: "ring-blue-500/30",
    label: "SQL Generation & Execution",
    description: "Generating & running SQL queries",
  },
  validation: {
    icon: <Check className="h-3 w-3" />,
    gradient: "from-emerald-500 to-green-500",
    border: "border-emerald-500/15",
    bg: "bg-emerald-500/[0.03]",
    accent: "text-emerald-500",
    ring: "ring-emerald-500/30",
    label: "Validation",
    description: "Validating data quality",
  },
  sql_executor: {
    icon: <Zap className="h-3 w-3" />,
    gradient: "from-amber-500 to-orange-500",
    border: "border-amber-500/15",
    bg: "bg-amber-500/[0.03]",
    accent: "text-amber-500",
    ring: "ring-amber-500/30",
    label: "SQL Execution",
    description: "Executing SQL queries",
  },
  chart: {
    icon: <BarChart3 className="h-3 w-3" />,
    gradient: "from-pink-500 to-rose-500",
    border: "border-pink-500/15",
    bg: "bg-pink-500/[0.03]",
    accent: "text-pink-500",
    ring: "ring-pink-500/30",
    label: "Chart Builder",
    description: "Creating visualizations",
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
    border: "border-slate-500/15",
    bg: "bg-slate-500/[0.03]",
    accent: "text-slate-500",
    ring: "ring-slate-500/30",
    label: name,
    description: "Processing…",
  };
}

function formatAgentName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Format token count for human readability */
function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toLocaleString();
}

// ── Expanded member card (shows output inline) ───────────────
interface MemberCardProps {
  member: MemberRunData;
  isLast: boolean;
  stepNumber: number;
  onMemberClick?: (member: MemberRunData) => void;
}

const MemberCard = memo(function MemberCard({ member, isLast, stepNumber, onMemberClick }: MemberCardProps) {
  const style = getAgentStyle(member.name);
  const isRunning = member.status === "running";
  const hasError = member.status === "error";
  const isDone = member.status === "completed";

  const [contentExpanded, setContentExpanded] = useState(false);

  const hasContent = !!member.content;
  const hasOutput = hasContent || hasError || isRunning;

  return (
    <div className="relative animate-fade-in">
      {/* Timeline connector line */}
      {!isLast && (
        <div
          className={cn(
            "absolute bottom-0 left-[13px] top-[28px] w-[1.5px] transition-colors duration-500",
            isDone
              ? "bg-gradient-to-b from-emerald-500/25 to-emerald-500/5"
              : isRunning
                ? "bg-gradient-to-b from-primary/30 to-primary/5 animate-pulse"
                : "bg-gradient-to-b from-red-500/25 to-red-500/5"
          )}
        />
      )}

      {/* Agent header row */}
      <div className="relative flex items-start gap-3">
        {/* Timeline step indicator */}
        <div className="relative z-10 mt-0.5 flex shrink-0">
          <div
            className={cn(
              "flex h-[26px] w-[26px] items-center justify-center rounded-full transition-all duration-300 text-[10px] font-bold",
              isRunning && "bg-primary/10 ring-2 ring-primary/30 text-primary animate-pulse-ring",
              isDone && "bg-emerald-500/10 ring-1 ring-emerald-500/20 text-emerald-600",
              hasError && "bg-red-500/10 ring-1 ring-red-500/20 text-red-500"
            )}
          >
            {isRunning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            ) : isDone ? (
              <Check className="h-3 w-3 text-emerald-500" />
            ) : (
              <X className="h-3 w-3 text-red-500" />
            )}
          </div>
        </div>

        {/* Agent info + collapsible content */}
        <div className="min-w-0 flex-1 overflow-hidden pb-4">
          {/* Agent name header */}
          <button
            type="button"
            onClick={() => hasOutput && setContentExpanded((v) => !v)}
            className={cn(
              "flex w-full items-center gap-2 text-left group/agent rounded-lg px-2 py-1.5 -ml-2 transition-colors",
              hasOutput && "hover:bg-accent/50 cursor-pointer",
              !hasOutput && "cursor-default"
            )}
          >
            {/* Step number badge */}
            <span className="flex h-4 w-4 items-center justify-center rounded text-[9px] font-bold text-muted-foreground/40 bg-muted/30">
              {stepNumber}
            </span>
            {/* Agent icon */}
            <div
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-lg bg-gradient-to-br text-white shadow-sm transition-transform group-hover/agent:scale-105",
                style.gradient
              )}
            >
              <span className="scale-[0.65]">{style.icon}</span>
            </div>
            {/* Agent name & description */}
            <div className="min-w-0 flex-1">
              <span className="truncate text-[11px] font-semibold text-foreground/80 leading-none">
                {formatAgentName(member.name)}
              </span>
              {isRunning && !hasContent && (
                <span className="block text-[10px] text-muted-foreground/50 mt-0.5">
                  {style.description}
                </span>
              )}
            </div>
            {/* Status badges */}
            {member.model && isDone && (
              <span className="hidden sm:inline-block rounded-full bg-muted/40 px-1.5 py-0.5 text-[9px] text-muted-foreground/40 font-medium">
                {member.model}
              </span>
            )}
            {isDone && member.total_tokens ? (
              <span className="shrink-0 rounded-full bg-emerald-500/8 px-2 py-0.5 text-[10px] tabular-nums text-emerald-600/60 font-medium">
                {formatTokens(member.total_tokens)} tok
              </span>
            ) : null}
            {isRunning && (
              <span className="ml-auto flex items-center gap-1.5 shrink-0">
                <span className="text-[10px] font-medium text-primary/60">working</span>
                <span className="flex items-center gap-0.5">
                  <span className="h-1 w-1 animate-bounce rounded-full bg-primary/50 [animation-delay:-0.3s]" />
                  <span className="h-1 w-1 animate-bounce rounded-full bg-primary/50 [animation-delay:-0.15s]" />
                  <span className="h-1 w-1 animate-bounce rounded-full bg-primary/50" />
                </span>
              </span>
            )}
            {hasOutput && (
              <span className="text-muted-foreground/30 transition-transform">
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
              "mt-1.5 overflow-hidden rounded-xl border shadow-sm transition-all animate-slide-down",
              style.border, style.bg,
              isRunning && "shadow-primary/5",
              isDone && "shadow-emerald-500/5",
            )}>
              {/* Scrollable inner content */}
              <div className="max-h-[350px] overflow-y-auto overscroll-contain p-3.5 space-y-2">
                {/* Streaming content (output only) */}
                {hasContent && (
                  <div className="min-w-0 overflow-hidden text-[12px] leading-relaxed text-foreground/80">
                    <div className="overflow-x-auto break-words [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_code]:break-all [&_table]:w-full [&_table]:table-fixed [&_td]:break-words [&_th]:break-words [&_img]:max-w-full [&_img]:h-auto">
                      <MarkdownContent content={member.content} />
                    </div>
                    {isRunning && (
                      <span
                        className="ml-0.5 inline-block h-3 w-1 animate-pulse rounded-sm bg-primary align-text-bottom"
                        aria-label="Streaming"
                      />
                    )}
                  </div>
                )}

                {/* Running but no content yet */}
                {isRunning && !hasContent && (
                  <div className="flex items-center gap-2.5 py-2">
                    <Loader2 className={cn("h-3.5 w-3.5 animate-spin", style.accent)} />
                    <span className="text-[11px] text-muted-foreground">
                      Agent is working…
                    </span>
                  </div>
                )}

                {/* Error block */}
                {hasError && member.error && (
                  <div className="flex items-start gap-2 rounded-lg border border-red-500/15 bg-red-500/5 px-3 py-2.5">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] font-semibold text-red-600 dark:text-red-400">Error</p>
                      <p className="mt-0.5 break-words text-[11px] leading-relaxed text-red-600/80 dark:text-red-400/80">
                        {member.error}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* View full detail link — sticky footer outside scroll */}
              {isDone && hasContent && onMemberClick && (
                <div className="border-t border-inherit px-3.5 py-2">
                  <button
                    type="button"
                    onClick={() => onMemberClick(member)}
                    className="flex items-center gap-1.5 rounded-full border border-primary/10 bg-primary/[0.03] px-3 py-1.5 text-[10px] font-medium text-primary/60 transition-all hover:border-primary/20 hover:bg-primary/5 hover:text-primary"
                  >
                    <Eye className="h-2.5 w-2.5" />
                    View full output
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

// ── Main delegation block (timeline) ─────────────────────────
interface AgentDelegationBlockProps {
  members: MemberRunData[];
  onMemberClick?: (member: MemberRunData) => void;
}

export const AgentDelegationBlock = memo(function AgentDelegationBlock({ members, onMemberClick }: AgentDelegationBlockProps) {
  if (!members.length) return null;

  const completedCount = members.filter((m) => m.status === "completed").length;
  const runningCount = members.filter((m) => m.status === "running").length;
  const errorCount = members.filter((m) => m.status === "error").length;
  const totalTokens = members.reduce((sum, m) => sum + (m.total_tokens || 0), 0);
  const allDone = runningCount === 0 && members.length > 0;

  // Progress percentage for visual indicator
  const progress = members.length > 0 ? Math.round(((completedCount + errorCount) / members.length) * 100) : 0;

  return (
    <div className="min-w-0 space-y-2.5" role="list" aria-label="Agent team workflow">
      {/* Compact summary bar */}
      <div
        className={cn(
          "overflow-hidden rounded-xl border shadow-sm transition-all",
          allDone
            ? "border-emerald-500/15 bg-gradient-to-r from-emerald-500/[0.06] via-emerald-500/[0.03] to-transparent"
            : "border-primary/15 bg-gradient-to-r from-primary/[0.06] via-primary/[0.03] to-transparent"
        )}
      >
        {/* Progress bar (thin line at top) */}
        {!allDone && (
          <div className="h-[2px] w-full bg-muted/20">
            <div
              className="h-full bg-gradient-to-r from-primary/60 to-primary/30 transition-all duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
        
        <div className="flex flex-wrap items-center gap-2 px-3.5 py-2.5 sm:flex-nowrap sm:gap-3">
          {/* Team icon */}
          <div className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-all",
            allDone
              ? "bg-emerald-500/10 ring-1 ring-emerald-500/15"
              : "bg-primary/10 ring-1 ring-primary/15"
          )}>
            {allDone ? (
              <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <Users className="h-3.5 w-3.5 text-primary/60" />
            )}
          </div>

          {/* Info text */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground/80">
                {allDone ? "Workflow Complete" : "Agent Workflow"}
              </span>
              {runningCount > 0 && (
                <Loader2 className="h-3 w-3 animate-spin text-primary/60" />
              )}
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground/50">
              <span>{members.length} agent{members.length > 1 ? "s" : ""}</span>
              {completedCount > 0 && (
                <>
                  <span className="text-muted-foreground/20">·</span>
                  <span className="flex items-center gap-0.5">
                    <Check className="h-2.5 w-2.5 text-emerald-500/60" />
                    <span className="text-emerald-600/60">{completedCount} done</span>
                  </span>
                </>
              )}
              {runningCount > 0 && (
                <>
                  <span className="text-muted-foreground/20">·</span>
                  <span className="text-primary/60">{runningCount} running</span>
                </>
              )}
              {errorCount > 0 && (
                <>
                  <span className="text-muted-foreground/20">·</span>
                  <span className="flex items-center gap-0.5">
                    <AlertTriangle className="h-2.5 w-2.5 text-red-500/60" />
                    <span className="text-red-500/60">{errorCount} error</span>
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Token badge */}
          {totalTokens > 0 && (
            <span className="hidden shrink-0 items-center gap-1 rounded-full bg-muted/40 px-2 py-0.5 text-[10px] tabular-nums text-muted-foreground/50 sm:inline-flex">
              <Clock className="h-2.5 w-2.5" />
              {formatTokens(totalTokens)} tokens
            </span>
          )}
        </div>
      </div>

      {/* Agent pipeline steps */}
      <div className="pl-2">
        {members.map((member, idx) => (
          <MemberCard
            key={member.id}
            member={member}
            isLast={idx === members.length - 1}
            stepNumber={idx + 1}
            onMemberClick={onMemberClick}
          />
        ))}
      </div>
    </div>
  );
});
