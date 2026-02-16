"use client";

import { cn } from "@/lib/utils";
import { Bot, User, Copy, Check } from "lucide-react";
import { SQLBlock } from "./sql-block";
import { MarkdownContent } from "./markdown-content";
import { ThinkingBlock } from "./thinking-block";
import { ToolCallList } from "./tool-call-block";
import { Badge } from "@/components/ui/badge";
import { useClipboard } from "@/hooks/use-clipboard";
import { ChatResponse, INTENT_LABELS, ToolCallData, ReasoningData } from "@/types";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  metadata?: ChatResponse;
  streaming?: boolean;
  reasoning?: ReasoningData;
  toolCalls?: ToolCallData[];
  onSuggestionClick?: (suggestion: string) => void;
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
  onSuggestionClick,
}: ChatMessageProps) {
  const isUser = role === "user";
  const { copied, copy } = useClipboard();

  return (
    <div
      className={cn(
        "group relative px-3 py-4 transition-colors sm:px-4 sm:py-5",
        isUser
          ? "bg-transparent"
          : "bg-muted/20"
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
                : "h-7 w-7 bg-gradient-to-br from-violet-500/15 to-blue-500/15 text-primary ring-1 ring-primary/10 sm:h-8 sm:w-8"
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
        <div className="min-w-0 flex-1 space-y-2.5 sm:space-y-3">
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

          {/* Thinking / reasoning block */}
          {!isUser && reasoning && (reasoning.content || reasoning.isActive) && (
            <ThinkingBlock
              content={reasoning.content}
              isActive={reasoning.isActive}
            />
          )}

          {/* Tool calls */}
          {!isUser && toolCalls && toolCalls.length > 0 && (
            <ToolCallList toolCalls={toolCalls} />
          )}

          {/* Message content */}
          {isUser ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {content}
            </p>
          ) : (
            <div className="text-sm leading-relaxed">
              <MarkdownContent content={content} />
              {streaming && (
                <span
                  className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-text-bottom rounded-sm"
                  aria-label="Typing indicator"
                />
              )}
            </div>
          )}

          {/* SQL block */}
          {metadata?.sql && (
            <SQLBlock
              sql={metadata.sql}
              tablesUsed={metadata.tables_used}
              isValid={metadata.is_valid}
              errors={metadata.errors}
              warnings={metadata.warnings}
            />
          )}

          {/* Suggestions */}
          {metadata?.suggestions && metadata.suggestions.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1 sm:gap-2">
              {metadata.suggestions.map((suggestion, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => onSuggestionClick?.(suggestion)}
                  className="cursor-pointer rounded-full border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-all hover:border-primary/30 hover:bg-primary/5 hover:text-foreground"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Copy button (assistant only) */}
        {!isUser && content && (
          <div className="shrink-0 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
            <button
              type="button"
              onClick={() => copy(content)}
              className={cn(
                "rounded-md p-1.5 transition-colors",
                copied
                  ? "text-emerald-500"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
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
