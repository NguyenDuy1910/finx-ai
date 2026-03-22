"use client";

import { useState, useRef, useEffect, useCallback, useMemo, memo, FormEvent } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { Loader2, ArrowDown, Square, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { ChatMessage } from "./chat-message";
import { ChatInput } from "./chat-input";
import { ChatWelcome } from "./chat-welcome";
import { ChatModeSwitcher } from "./chat-mode-switcher";
import { AgentDetailSidePanel } from "./agent-detail-side-panel";
import { SourcePreviewPanel } from "./source-preview-panel";
import { ResizeHandle } from "./resize-handle";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { useChatDataParts } from "@/hooks/use-chat-data-parts";
import { parseKnowledgeFromToolCalls } from "./knowledge-panel";
import { parseChartSpecFromToolCalls } from "./chart-block";
import { saveMessageCache, loadMessageCache, type CachedMessage } from "@/lib/chat-store";
import type { MemberRunData, ChatMode } from "@/types";

interface ChatContainerProps {
  database: string;
  threadId: string;
  initialSessionId?: string | null;
  initialMode?: ChatMode;
  onSessionEstablished?: (sessionId: string) => void;
  onFirstMessage?: (message: string) => void;
  onModeChange?: (mode: ChatMode) => void;
}

const API_ROUTES: Record<ChatMode, string> = {
  agent: "/api/agent-chat",
  team: "/api/team-chat",
  knowledge: "/api/agent-chat",
};

const AGENT_IDS: Partial<Record<ChatMode, string>> = {
  agent: "confluence-researcher",
  knowledge: "company-knowledge",
};

export function ChatContainer({
  database: _database,
  threadId,
  initialSessionId,
  initialMode = "agent",
  onSessionEstablished,
  onFirstMessage,
  onModeChange,
}: ChatContainerProps) {
  const [input, setInput] = useState("");
  const [chatMode, setChatMode] = useState<ChatMode>(initialMode);
  const sessionIdRef = useRef<string | undefined>(initialSessionId ?? undefined);
  const hasNotifiedSessionRef = useRef(false);
  const hasNotifiedFirstMsgRef = useRef(false);
  const chatModeRef = useRef<ChatMode>(initialMode);

  // ── Right-side detail panel ──────────────────────────────────
  const [selectedMember, setSelectedMember] = useState<MemberRunData | null>(null);
  const [selectedMemberMessageId, setSelectedMemberMessageId] = useState<string | null>(null);
  const selectedMemberMessageIdRef = useRef<string | null>(null);

  // ── Source preview panel ──────────────────────────────────────
  const [selectedCitation, setSelectedCitation] = useState<import("@/types").CitationData | null>(null);
  const [selectedCitationAllSources, setSelectedCitationAllSources] = useState<import("@/types").CitationData[]>([]);

  // ── Resizable side panel ──────────────────────────────────────
  const [panelWidth, setPanelWidth] = useState(400);

  // ── Cached message history (restored from localStorage) ─────
  const [cachedMessages, setCachedMessages] = useState<CachedMessage[]>(() => loadMessageCache(threadId));

  const handleCitationClick = useCallback((citation: import("@/types").CitationData, allCitations: import("@/types").CitationData[]) => {
    // Clicking a citation closes the member panel and opens the source panel
    setSelectedMember(null);
    setSelectedMemberMessageId(null);
    selectedMemberMessageIdRef.current = null;
    setSelectedCitation((prev) => (prev?.id === citation.id ? null : citation));
    setSelectedCitationAllSources(allCitations);
  }, []);

  const handleCloseSourcePanel = useCallback(() => {
    setSelectedCitation(null);
  }, []);

  const handleMemberClick = useCallback((member: MemberRunData, messageId: string) => {
    // Close source panel when opening member panel
    setSelectedCitation(null);
    setSelectedMember((prev) => {
      const isSame = prev?.id === member.id && selectedMemberMessageIdRef.current === messageId;
      if (isSame) {
        selectedMemberMessageIdRef.current = null;
        setSelectedMemberMessageId(null);
        return null;
      }
      selectedMemberMessageIdRef.current = messageId;
      setSelectedMemberMessageId(messageId);
      return member;
    });
  }, []);

  const handleClosePanel = useCallback(() => {
    setSelectedMember(null);
    setSelectedMemberMessageId(null);
    selectedMemberMessageIdRef.current = null;
  }, []);

  // ── Session id handling ──────────────────────────────────────
  const handleSessionId = useCallback(
    (sid: string) => {
      sessionIdRef.current = sid;
      if (!hasNotifiedSessionRef.current && onSessionEstablished) {
        hasNotifiedSessionRef.current = true;
        onSessionEstablished(sid);
      }
    },
    [onSessionEstablished]
  );

  // ── Mode switching ───────────────────────────────────────────
  const handleModeSwitch = useCallback(
    (newMode: ChatMode) => {
      setChatMode(newMode);
      chatModeRef.current = newMode;
      onModeChange?.(newMode);
    },
    [onModeChange]
  );

  // ── Transport (recreated only when chatMode changes) ─────────
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: API_ROUTES[chatMode],
        body: () => ({
          session_id: sessionIdRef.current,
          ...(AGENT_IDS[chatModeRef.current] ? { agent_id: AGENT_IDS[chatModeRef.current] } : {}),
        }),
      }),
    [chatMode]
  );

  const {
    messages: agentMessages,
    sendMessage,
    status,
    error: agentError,
    stop,
  } = useChat({
    id: `${threadId}-${chatMode}`,
    transport,
    experimental_throttle: 100,
    onFinish: ({ message }) => {
      markRunsComplete(message.id);
      // Session id may also arrive in the final message parts
      const sessionPart = message.parts.find((p) => p.type === "data-session");
      if (sessionPart && "data" in sessionPart) {
        const d = (sessionPart as { data: { session_id?: string } }).data;
        if (d.session_id) handleSessionId(d.session_id);
      }
    },
    onData: (dataPart) => {
      if (!dataPart || typeof dataPart !== "object") return;
      const part = dataPart as Record<string, unknown>;
      if ("session_id" in part) handleSessionId(part.session_id as string);
    },
    onError: (error) => {
      console.error("Agent chat error:", error);
    },
  });

  // ── Data-parts processing (extracted hook) ───────────────────
  const { reasoningMap, toolCallMap, memberRunMap, metricsMap, citationsMap, activityMap, markRunsComplete } =
    useChatDataParts(agentMessages, { onSessionId: handleSessionId });

  // Keep side-panel member data in sync with streaming updates
  useEffect(() => {
    if (!selectedMember || !selectedMemberMessageId) return;
    const membersForMessage = memberRunMap[selectedMemberMessageId];
    if (!membersForMessage) return;
    const updated = membersForMessage.find((m) => m.id === selectedMember.id);
    if (updated && updated !== selectedMember) setSelectedMember(updated);
  }, [memberRunMap, selectedMember, selectedMemberMessageId]);

  // ── Send / retry ─────────────────────────────────────────────
  const isAgentBusy = status === "submitted" || status === "streaming";
  const isStreaming = status === "streaming";
  const showLoader = status === "submitted";

  const handleSend = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isAgentBusy) return;
      if (!hasNotifiedFirstMsgRef.current && onFirstMessage) {
        hasNotifiedFirstMsgRef.current = true;
        onFirstMessage(trimmed);
      }
      setInput("");
      sendMessage({ text: trimmed });
    },
    [isAgentBusy, sendMessage, onFirstMessage]
  );

  const handleRetry = useCallback(() => {
    const lastUserMsg = [...agentMessages].reverse().find((m) => m.role === "user");
    if (lastUserMsg) {
      const text = lastUserMsg.parts
        .filter((p) => p.type === "text")
        .map((p) => (p as { text: string }).text)
        .join("");
      if (text) sendMessage({ text });
    }
  }, [agentMessages, sendMessage]);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      handleSend(input);
    },
    [input, handleSend]
  );

  // ── Auto-scroll ──────────────────────────────────────────────
  const { bottomRef, scrollContainerRef, showScrollBtn, handleScroll, scrollToBottom } =
    useAutoScroll([agentMessages, isAgentBusy, reasoningMap, toolCallMap, memberRunMap]);

  // ── Render list ──────────────────────────────────────────────
  const liveMessages = useMemo(
    () =>
      agentMessages.map((m) => {
        const members = memberRunMap[m.id];
        const tcs = toolCallMap[m.id];

        let chartSpec = null;
        if (members) {
          for (const member of members) {
            if (member.name === "Chart Builder Agent" && member.toolCalls) {
              chartSpec = parseChartSpecFromToolCalls(member.toolCalls);
              if (chartSpec) break;
            }
          }
        }
        if (!chartSpec && tcs) chartSpec = parseChartSpecFromToolCalls(tcs);

        return {
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.parts
            .filter((p) => p.type === "text")
            .map((p) => (p as { text: string }).text)
            .join(""),
          streaming: isStreaming && m.role === "assistant" && m === agentMessages[agentMessages.length - 1],
          reasoning: reasoningMap[m.id],
          toolCalls: tcs,
          memberRuns: members,
          runMetrics: metricsMap[m.id],
          knowledgeData: tcs ? parseKnowledgeFromToolCalls(tcs) : null,
          chartData: chartSpec,
          citations: citationsMap[m.id],
          activity: activityMap[m.id],
        };
      }),
    [agentMessages, isStreaming, reasoningMap, toolCallMap, memberRunMap, metricsMap, citationsMap, activityMap]
  );

  // Persist messages to cache whenever a non-streaming snapshot is available
  useEffect(() => {
    if (liveMessages.length > 0 && !isAgentBusy) {
      saveMessageCache(threadId, liveMessages);
      // Clear cached fallback once live messages exist
      if (cachedMessages.length > 0) setCachedMessages([]);
    }
  }, [liveMessages, isAgentBusy, threadId, cachedMessages.length]);

  // Use live messages when available, fall back to cached history
  const renderMessages = liveMessages.length > 0 ? liveMessages : cachedMessages.map((m) => ({
    ...m,
    streaming: false,
    knowledgeData: null as import("./knowledge-panel").KnowledgeData | null,
    chartData: null as import("./chart-block").ChartSpec | null,
  }));

  const hasMessages = renderMessages.length > 0;

  const isPanelOpen = !!(selectedMember || selectedCitation);

  return (
    <div className="relative flex h-full overflow-hidden">
      {/* ── Chat thread area ──────────────────────────────────── */}
      <div className="relative flex min-w-0 flex-1 flex-col">

        {/* ── Scrollable message list ──────────────────────────── */}
        <ScrollArea
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overscroll-contain"
        >
          {/* Accessible live region */}
          <div aria-live="polite" aria-atomic="false" className="sr-only">
            {hasMessages && (
              <span>
                {renderMessages[renderMessages.length - 1].role === "assistant"
                  ? "New response from FinX AI"
                  : "Message sent"}
              </span>
            )}
          </div>

          {!hasMessages && (
            <ChatWelcome mode={chatMode} onSuggestionClick={handleSend} />
          )}

          {hasMessages && (
            <div className="px-4 sm:px-6 pb-6 pt-6 sm:pt-8">
              <div className="mx-auto max-w-[var(--chat-max-width,760px)]">
              {renderMessages.map((message, index) => (
                <MemoizedMessage
                  key={message.id}
                  messageId={message.id}
                  index={index}
                  role={message.role}
                  content={message.content}
                  streaming={message.streaming}
                  reasoning={message.reasoning}
                  toolCalls={message.toolCalls}
                  memberRuns={message.memberRuns}
                  knowledgeData={message.knowledgeData}
                  chartData={message.chartData}
                  citations={message.citations}
                  activity={message.activity}
                  onSuggestionClick={handleSend}
                  onMemberClick={handleMemberClick}
                  onCitationClick={handleCitationClick}
                />
              ))}
              </div>
            </div>
          )}

          {/* Error with retry */}
          {agentError && (
            <div className="mx-auto max-w-[var(--chat-max-width,760px)] px-4 py-3 animate-message-in">
              <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium">Something went wrong</p>
                    <p className="mt-1 truncate text-xs opacity-70">
                      {agentError.message || "Please try again."}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleRetry}
                    className="flex shrink-0 items-center gap-1.5 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-1.5 text-xs font-medium text-destructive transition-all hover:bg-destructive/15 active:scale-95"
                  >
                    <RefreshCw className="h-3 w-3" />
                    Retry
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Typing / thinking indicator */}
          {showLoader && (
            <div className="px-4 py-5 animate-message-in">
              <div className="mx-auto flex max-w-[var(--chat-max-width,760px)] gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                </div>
                <div className="flex items-center gap-2 pt-0.5">
                  <span className="text-[0.8125rem] font-medium text-muted-foreground/60">FinX AI is thinking</span>
                  <div className="flex items-center gap-0.5">
                    <span className="h-1 w-1 animate-bounce rounded-full bg-primary/40 [animation-delay:-0.3s]" />
                    <span className="h-1 w-1 animate-bounce rounded-full bg-primary/40 [animation-delay:-0.15s]" />
                    <span className="h-1 w-1 animate-bounce rounded-full bg-primary/40" />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} className="h-6" />
        </ScrollArea>

        {/* ── Scroll to bottom FAB ─────────────────────────────── */}
        {showScrollBtn && (
          <div className="absolute bottom-28 left-1/2 z-10 -translate-x-1/2">
            <button
              type="button"
              onClick={scrollToBottom}
              className="flex items-center gap-1.5 rounded-full border border-border/60 bg-background/95 px-3 py-1.5 text-xs text-muted-foreground shadow-lg shadow-black/5 backdrop-blur-md transition-all hover:bg-accent hover:text-foreground hover:shadow-xl active:scale-95 animate-scale-in"
              aria-label="Scroll to bottom"
            >
              <ArrowDown className="h-3 w-3" />
              <span className="hidden sm:inline">New messages</span>
            </button>
          </div>
        )}

        {/* ── Composer ── */}
        <div className="shrink-0 border-t border-border bg-background px-4 py-3 shadow-[0_-1px_3px_0_rgba(0,0,0,0.04)] sm:px-5 sm:py-4">
          <div className="mx-auto max-w-[var(--chat-max-width,760px)]">
            <div className="mb-2 flex items-center justify-between">
              <ChatModeSwitcher
                mode={chatMode}
                onModeChange={handleModeSwitch}
                isDisabled={isAgentBusy}
              />
              {isAgentBusy && (
                <button
                  type="button"
                  onClick={stop}
                  className="flex items-center gap-1.5 rounded-full border border-border/60 bg-background/90 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-all hover:border-destructive/30 hover:bg-destructive/5 hover:text-destructive active:scale-95"
                  aria-label="Stop generating"
                >
                  <Square className="h-3 w-3" />
                  Stop
                </button>
              )}
            </div>

            <ChatInput
              value={input}
              onChange={setInput}
              onSubmit={handleSubmit}
              isLoading={isAgentBusy}
              placeholder={
                chatMode === "team"
                  ? "Ask the FinX team anything..."
                  : chatMode === "knowledge"
                    ? "Ask about company policies, procedures, or documentation..."
                    : "Ask the agent anything..."
              }
            />
          </div>
        </div>
      </div>

      {/* ── Resize handle (only when panel is open) ─────────────── */}
      {isPanelOpen && (
        <ResizeHandle
          onResize={setPanelWidth}
          minWidth={300}
          maxWidth={640}
          className="hidden lg:block"
        />
      )}

      {/* ── Right-side contextual panel (resizable) ─────────────── */}
      <div
        className={cn(
          "hidden shrink-0 overflow-hidden transition-[width,opacity] duration-200 ease-out lg:block",
          isPanelOpen ? "opacity-100" : "w-0 opacity-0"
        )}
        style={isPanelOpen ? { width: panelWidth } : undefined}
      >
        {selectedMember && (
          <AgentDetailSidePanel
            member={selectedMember}
            onClose={handleClosePanel}
          />
        )}
        {selectedCitation && !selectedMember && (
          <SourcePreviewPanel
            citation={selectedCitation}
            allCitations={selectedCitationAllSources}
            onClose={handleCloseSourcePanel}
            onSelectCitation={(c) => {
              setSelectedCitation(c);
            }}
          />
        )}
      </div>

      {/* ── Mobile bottom sheet for source preview ─────────────── */}
      {selectedCitation && !selectedMember && (
        <div className="fixed inset-x-0 bottom-0 z-50 lg:hidden animate-in slide-in-from-bottom duration-200">
          <div
            className="mx-auto max-h-[70vh] overflow-hidden rounded-t-2xl border border-border/60 bg-background shadow-2xl"
          >
            <div className="max-h-[70vh] overflow-y-auto overscroll-contain">
              <SourcePreviewPanel
                citation={selectedCitation}
                allCitations={selectedCitationAllSources}
                onClose={handleCloseSourcePanel}
                onSelectCitation={(c) => {
                  setSelectedCitation(c);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Memoized message wrapper ──────────────────────────────────────

interface MemoizedMessageProps {
  messageId: string;
  index: number;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  reasoning?: import("@/types").ReasoningData;
  toolCalls?: import("@/types").ToolCallData[];
  memberRuns?: import("@/types").MemberRunData[];
  knowledgeData?: import("./knowledge-panel").KnowledgeData | null;
  chartData?: import("./chart-block").ChartSpec | null;
  citations?: import("@/types").CitationData[];
  activity?: import("@/types").ActivityData;
  onSuggestionClick: (text: string) => void;
  onMemberClick?: (member: MemberRunData, messageId: string) => void;
  onCitationClick?: (citation: import("@/types").CitationData, allCitations: import("@/types").CitationData[]) => void;
}

const MemoizedMessage = memo(function MemoizedMessage({
  messageId,
  index,
  role,
  content,
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
}: MemoizedMessageProps) {
  return (
    <div
      className={`animate-message-in${streaming ? " streaming-active" : ""}`}
      style={{ animationDelay: `${Math.min(index * 30, 150)}ms` }}
    >
      <ChatMessage
        messageId={messageId}
        role={role}
        content={content}
        streaming={streaming}
        reasoning={reasoning}
        toolCalls={toolCalls}
        memberRuns={memberRuns}
        knowledgeData={knowledgeData}
        chartData={chartData}
        citations={citations}
        activity={activity}
        onSuggestionClick={onSuggestionClick}
        onMemberClick={onMemberClick}
        onCitationClick={onCitationClick}
      />
    </div>
  );
});
