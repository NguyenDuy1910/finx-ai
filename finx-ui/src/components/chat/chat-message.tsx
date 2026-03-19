"use client";

import { memo, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import { User, Copy, Check, Sparkles, Search, BookOpen, Loader2 } from "lucide-react";
import { SQLBlock } from "./sql-block";
import { MarkdownContent } from "./markdown-content";
import { AgentDelegationBlock } from "./agent-delegation-block";
import { ToolCallList } from "./tool-call-block";
import { KnowledgePanel, type KnowledgeData } from "./knowledge-panel";
import { ChartBlock, parseChartSpecFromToolCalls, type ChartSpec } from "./chart-block";
import { CitationPanel } from "./citation-panel";
import { Badge } from "@/components/ui/badge";
import { ThinkingBlock } from "./thinking-block";
import { useClipboard } from "@/hooks/use-clipboard";
import { INTENT_LABELS, ToolCallData, ReasoningData, MemberRunData, CitationData, ActivityData } from "@/types";

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
  messageId?: string;
  role: "user" | "assistant";
  content: string;
  metadata?: MessageMetadata;
  streaming?: boolean;
  reasoning?: ReasoningData;
  toolCalls?: ToolCallData[];
  memberRuns?: MemberRunData[];
  knowledgeData?: KnowledgeData | null;
  chartData?: ChartSpec | null;
  citations?: CitationData[];
  activity?: ActivityData;
  onSuggestionClick?: (suggestion: string) => void;
  onMemberClick?: (member: MemberRunData, messageId: string) => void;
  onCitationClick?: (citation: CitationData, allCitations: CitationData[]) => void;
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

/** Subtle inline activity indicator shown while streaming. */
function ActivityStatusRow({
  activity,
  streaming,
}: {
  activity: ActivityData;
  streaming: boolean;
}) {
  if (!streaming) return null;
  if (activity.status === "idle" || activity.status === "done") return null;

  const labels: Record<ActivityData["status"], string> = {
    idle: "",
    searching: "Searching knowledge base",
    reading: "Reading sources",
    reranking: "Reranking results",
    drafting: "Drafting answer",
    done: "",
  };

  const label = labels[activity.status] || "Processing";
  const query = activity.query;

  return (
    <div className="flex items-center gap-2 rounded-lg border border-primary/10 bg-primary/[0.04] px-2.5 py-1.5">
      {activity.status === "searching" ? (
        <Search className="h-3 w-3 shrink-0 text-primary/50" />
      ) : (
        <BookOpen className="h-3 w-3 shrink-0 text-primary/50" />
      )}
      <span className="text-[0.75rem] text-primary/60 font-medium">
        {label}
        {query ? (
          <span className="ml-1 font-normal text-muted-foreground/50">
            &ldquo;{query.length > 60 ? query.slice(0, 60) + "…" : query}&rdquo;
          </span>
        ) : null}
      </span>
      <Loader2 className="ml-auto h-2.5 w-2.5 animate-spin text-primary/40" />
    </div>
  );
}

export const ChatMessage = memo(function ChatMessage({
  messageId,
  role,
  content,
  metadata,
  streaming,
  reasoning,
  toolCalls,
  memberRuns,
  knowledgeData,
  chartData,
  citations,
  activity,
  onSuggestionClick,
  onMemberClick,
  onCitationClick,
}: ChatMessageProps) {
  const isUser = role === "user";
  const { copied, copy } = useClipboard();

  const handleMemberClick = useCallback(
    (member: MemberRunData) => {
      if (onMemberClick && messageId) onMemberClick(member, messageId);
    },
    [onMemberClick, messageId]
  );

  const resolvedChart = useMemo<ChartSpec | null>(() => {
    if (chartData) return chartData;
    if (!memberRuns) return null;
    for (const member of memberRuns) {
      if (member.name === "Chart Builder Agent" && member.toolCalls) {
        const spec = parseChartSpecFromToolCalls(member.toolCalls);
        if (spec) return spec;
      }
    }
    return parseChartSpecFromToolCalls(toolCalls) ?? null;
  }, [chartData, memberRuns, toolCalls]);

  const hasMemberRuns = !isUser && memberRuns && memberRuns.length > 0;
  const hasCitations = !isUser && citations && citations.length > 0;
  const showActivity = !isUser && streaming && activity && activity.status !== "idle" && activity.status !== "done";

  return (
    <div
      className={cn(
        "group relative animate-message-in",
        isUser ? "px-4 py-4 sm:px-6" : "px-4 py-5 sm:px-6 sm:py-6"
      )}
      role="article"
      aria-label={`${isUser ? "Your" : "FinX AI"} message`}
    >
      {isUser ? (
        /* ── User message — clean right-aligned bubble ── */
        <div className="mx-auto flex max-w-[var(--chat-max-width,760px)] items-start justify-end gap-3">
          <div className="flex max-w-[72%] flex-col items-end gap-1">
            <div className="rounded-2xl rounded-tr-md bg-primary px-4 py-3 shadow-sm">
              <p className="whitespace-pre-wrap text-[0.9375rem] leading-[1.65] text-primary-foreground">
                {content}
              </p>
            </div>
          </div>
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted ring-1 ring-border mt-0.5">
            <User className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
        </div>
      ) : (
        /* ── Assistant message ── */
        <div className="mx-auto max-w-[var(--chat-max-width,760px)]">
          {/* Role header */}
          <div className="mb-3 flex items-center gap-2.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
              <Sparkles className="h-3 w-3" />
            </div>
            <span className="text-[0.75rem] font-semibold text-foreground/60 tracking-[-0.005em]">
              FinX AI
            </span>
            {metadata?.intent && <IntentBadge intent={metadata.intent} />}
            {metadata?.database && (
              <span className="text-[0.6875rem] font-medium text-muted-foreground/40 tabular-nums ml-0.5">
                · {metadata.database}
              </span>
            )}
          </div>

          {/* Content area */}
          <div className="ml-[2.125rem] space-y-3">
            {/* Reasoning / thinking */}
            {reasoning && (reasoning.content || reasoning.isActive) && (
              <ThinkingBlock content={reasoning.content} isActive={reasoning.isActive} />
            )}

            {/* Activity status — only while streaming */}
            {showActivity && (
              <ActivityStatusRow activity={activity!} streaming={!!streaming} />
            )}

            {/* Agent delegation (team member runs) */}
            {memberRuns && memberRuns.length > 0 && (
              <AgentDelegationBlock members={memberRuns} onMemberClick={handleMemberClick} />
            )}

            {/* Tool calls (agent mode only, not team) */}
            {toolCalls && toolCalls.length > 0 && !hasMemberRuns && (
              <ToolCallList toolCalls={toolCalls} />
            )}

            {/* Message content */}
            {content ? (
              hasMemberRuns ? (
                /* ── Team response card ── */
                <div className="rounded-xl border border-border bg-surface-raised overflow-hidden">
                  <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                    <span className="text-[0.8125rem] font-semibold text-foreground/75">
                      Analysis
                    </span>
                    <span className="text-[0.75rem] text-muted-foreground/50">
                      from {memberRuns!.length} agent{memberRuns!.length > 1 ? "s" : ""}
                    </span>
                    {streaming && (
                      <span className="ml-auto flex items-center gap-1 text-[0.6875rem] text-primary/50">
                        <span className="h-1 w-1 animate-pulse rounded-full bg-primary/50" />
                        Streaming
                      </span>
                    )}
                  </div>
                  <div className="min-w-0 max-w-full overflow-hidden px-4 py-4">
                    <MarkdownContent content={content} className="team-summary-content" />
                    {streaming && (
                      <span
                        className="ml-0.5 inline-block h-[1.1em] w-1.5 animate-pulse rounded-sm bg-primary/70 align-text-bottom"
                        aria-label="Typing indicator"
                      />
                    )}
                  </div>
                </div>
              ) : (
                /* ── Standard assistant response ── */
                <div className="min-w-0 max-w-full overflow-hidden">
                  <MarkdownContent
                    content={content}
                    citations={citations}
                    onCitationClick={onCitationClick}
                  />
                  {streaming && (
                    <span
                      className="ml-0.5 inline-block h-[1.1em] w-1.5 animate-pulse rounded-sm bg-primary/70 align-text-bottom"
                      aria-label="Typing indicator"
                    />
                  )}
                </div>
              )
            ) : null}

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

            {/* Chart visualization */}
            {resolvedChart && <ChartBlock spec={resolvedChart} />}

            {/* Knowledge panel */}
            {knowledgeData && <KnowledgePanel data={knowledgeData} />}

            {/* Citations */}
            {hasCitations && (
              <CitationPanel
                citations={citations!}
                onCitationClick={onCitationClick ? (c) => onCitationClick(c, citations!) : undefined}
              />
            )}

            {/* Follow-up suggestions */}
            {metadata?.suggestions && metadata.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {metadata.suggestions.map((suggestion, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onSuggestionClick?.(suggestion)}
                    className="rounded-lg border border-border bg-background px-3 py-1.5 text-[0.8125rem] text-foreground/65 transition-all hover:border-border-strong hover:bg-accent hover:text-foreground active:scale-95"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Message actions — on hover */}
          {content && (
            <div className="chat-message-actions ml-[2.125rem] mt-2 flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
              <button
                type="button"
                onClick={() => copy(content)}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-2 py-1 text-[0.75rem] transition-all",
                  copied
                    ? "text-success"
                    : "text-muted-foreground/40 hover:bg-accent hover:text-muted-foreground"
                )}
                title={copied ? "Copied!" : "Copy response"}
                aria-label={copied ? "Copied to clipboard" : "Copy response"}
              >
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
              {hasCitations && onCitationClick && (
                <button
                  type="button"
                  onClick={() => onCitationClick(citations![0], citations!)}
                  className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-[0.75rem] text-muted-foreground/40 transition-all hover:bg-accent hover:text-muted-foreground"
                  title="View sources"
                  aria-label="View sources"
                >
                  <BookOpen className="h-3 w-3" />
                  <span>Sources</span>
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
