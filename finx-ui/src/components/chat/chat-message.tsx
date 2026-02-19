"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Bot, User, Copy, Check, ChevronDown, ChevronUp } from "lucide-react";
import { SQLBlock } from "./sql-block";
import { MarkdownContent } from "./markdown-content";
import { AgentDelegationBlock } from "./agent-delegation-block";
import { RunMetricsBlock } from "./run-metrics-block";
import { KnowledgePanel, type KnowledgeData } from "./knowledge-panel";
import { Badge } from "@/components/ui/badge";
import { useClipboard } from "@/hooks/use-clipboard";
import { INTENT_LABELS, ToolCallData, ReasoningData, MemberRunData, RunMetrics } from "@/types";

interface MessageMetadata {
  intent?: string;
  database?: string;
  sql?: string;
  tables_used?: string[];
  is_valid?: boolean;
  errors?: string[];
  warnings?: string[];
  suggestions?: string[];
}

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  metadata?: MessageMetadata;
  streaming?: boolean;
  reasoning?: ReasoningData;
  toolCalls?: ToolCallData[];
  memberRuns?: MemberRunData[];
  runMetrics?: RunMetrics;
  knowledgeData?: KnowledgeData | null;
  onSuggestionClick?: (suggestion: string) => void;
  onMemberClick?: (member: MemberRunData) => void;
}

function IntentBadge({ intent }: { intent: string }) {
  const label = INTENT_LABELS[intent] || intent;
  const variant =
    intent === "data_query"
      ? "default"
      : intent === "clarification"
        ? "warning"
        : "success";

  return (
    <Badge variant={variant} className="text-[10px]">
      {label}
    </Badge>
  );
}

export function ChatMessage({
  role,
  content,
  metadata,
  streaming,
  reasoning,
  toolCalls,
  memberRuns,
  runMetrics,
  knowledgeData,
  onSuggestionClick,
  onMemberClick,
}: ChatMessageProps) {
  const isUser = role === "user";
  const { copied, copy } = useClipboard();

  // Truncate long assistant content (> 600 chars) unless user expands
  const CONTENT_TRUNCATE_THRESHOLD = 600;
  const isLongContent = !isUser && content.length > CONTENT_TRUNCATE_THRESHOLD;
  const [contentExpanded, setContentExpanded] = useState(false);

  const displayContent =
    !isUser && isLongContent && !contentExpanded && !streaming
      ? content.slice(0, CONTENT_TRUNCATE_THRESHOLD).trimEnd() + "…"
      : content;

  return (
    <div
      className={cn(
        "group relative px-3 py-4 transition-colors sm:px-4 sm:py-5",
        isUser
          ? "bg-transparent"
          : "border-b border-border/5 bg-gradient-to-r from-muted/30 via-muted/10 to-transparent"
      )}
      role="article"
      aria-label={`${isUser ? "Your" : "FinX AI"} message`}
    >
      <div className="mx-auto flex max-w-3xl gap-3 sm:gap-4">
        {/* Avatar */}
        <div className="flex shrink-0 pt-0.5">
          <div
            className={cn(
              "flex items-center justify-center rounded-full transition-shadow",
              isUser
                ? "h-7 w-7 bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-sm sm:h-8 sm:w-8"
                : "h-7 w-7 bg-gradient-to-br from-violet-500/20 to-blue-500/20 text-primary ring-1 ring-primary/15 shadow-sm shadow-primary/5 sm:h-8 sm:w-8"
            )}
          >
            {isUser ? (
              <User className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            ) : (
              <Bot className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            )}
          </div>
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1 overflow-hidden space-y-3 sm:space-y-3.5">
          {/* Role label */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {isUser ? "You" : "FinX AI"}
            </span>
            {!isUser && metadata?.intent && (
              <IntentBadge intent={metadata.intent} />
            )}
            {!isUser && metadata?.database && (
              <span className="text-[10px] text-muted-foreground/60">
                {metadata.database}
              </span>
            )}
          </div>

          {/* Agent delegation (team member runs) */}
          {!isUser && memberRuns && memberRuns.length > 0 && (
            <AgentDelegationBlock members={memberRuns} onMemberClick={onMemberClick} />
          )}

          {/* Message content */}
          {isUser ? (
            <div className="inline-block max-w-[85%] rounded-2xl rounded-tl-sm bg-gradient-to-br from-emerald-500 to-teal-600 px-4 py-2.5 shadow-sm">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-white">
                {content}
              </p>
            </div>
          ) : (
            <div className="min-w-0 max-w-full overflow-hidden text-sm leading-relaxed">
              <MarkdownContent content={displayContent} />
              {streaming && (
                <span
                  className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-text-bottom rounded-sm"
                  aria-label="Typing indicator"
                />
              )}
              {/* Show more / less toggle for long content */}
              {isLongContent && !streaming && (
                <button
                  type="button"
                  onClick={() => setContentExpanded((v) => !v)}
                  className="mt-1.5 flex items-center gap-1 rounded-full border border-border/40 px-2.5 py-1 text-[11px] font-medium text-primary/70 transition-all hover:border-primary/20 hover:bg-primary/5 hover:text-primary"
                >
                  {contentExpanded ? (
                    <>
                      <ChevronUp className="h-3 w-3" />
                      Show less
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-3 w-3" />
                      Show full response ({content.length.toLocaleString()} chars)
                    </>
                  )}
                </button>
              )}
            </div>
          )}

          {/* SQL block */}
          {metadata?.sql && (
            <SQLBlock
              sql={metadata.sql}
              tablesUsed={metadata.tables_used ?? []}
              isValid={metadata.is_valid ?? false}
              errors={metadata.errors ?? []}
              warnings={metadata.warnings ?? []}
            />
          )}

          {/* Knowledge panel */}
          {!isUser && knowledgeData && (
            <KnowledgePanel data={knowledgeData} />
          )}

          {/* Run metrics (tokens, timing) */}
          {!isUser && runMetrics && (
            <RunMetricsBlock metrics={runMetrics} />
          )}

          {/* Suggestions */}
          {metadata?.suggestions && metadata.suggestions.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-2 sm:gap-2">
              {metadata.suggestions.map((suggestion, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => onSuggestionClick?.(suggestion)}
                  className="cursor-pointer rounded-full border border-primary/15 bg-primary/[0.03] px-3 py-1.5 text-xs text-primary/80 transition-all hover:border-primary/30 hover:bg-primary/8 hover:text-primary hover:shadow-sm active:scale-95"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Copy button (assistant only) */}
        {!isUser && content && (
          <div className="shrink-0 opacity-0 transition-all duration-200 group-hover:opacity-100">
            <button
              type="button"
              onClick={() => copy(content)}
              className={cn(
                "rounded-lg p-1.5 transition-all",
                copied
                  ? "text-emerald-500 bg-emerald-500/10"
                  : "text-muted-foreground/50 hover:bg-accent hover:text-foreground"
              )}
              title={copied ? "Copied!" : "Copy message"}
              aria-label={copied ? "Copied to clipboard" : "Copy message"}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
