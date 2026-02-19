"use client";

import { useState, useRef, useEffect, useCallback, useMemo, memo, FormEvent } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { Loader2, ArrowDown, Square, RefreshCw } from "lucide-react";
import { ChatMessage } from "./chat-message";
import { ChatInput } from "./chat-input";
import { ChatWelcome } from "./chat-welcome";
import { AgentDetailSidePanel } from "./agent-detail-side-panel";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { parseKnowledgeFromToolCalls } from "./knowledge-panel";
import type { ToolCallData, ReasoningData, MemberRunData, RunMetrics } from "@/types";

interface ChatContainerProps {
  database: string;
  threadId: string;
  initialSessionId?: string | null;
  onSessionEstablished?: (sessionId: string) => void;
  onFirstMessage?: (message: string) => void;
}

export function ChatContainer({
  database,
  threadId,
  initialSessionId,
  onSessionEstablished,
  onFirstMessage,
}: ChatContainerProps) {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>(
    initialSessionId ?? undefined
  );
  const sessionIdRef = useRef<string | undefined>(initialSessionId ?? undefined);
  const hasNotifiedSessionRef = useRef(false);
  const hasNotifiedFirstMsgRef = useRef(false);

  const [reasoningMap, setReasoningMap] = useState<Record<string, ReasoningData>>({});
  const [toolCallMap, setToolCallMap] = useState<Record<string, ToolCallData[]>>({});
  const [memberRunMap, setMemberRunMap] = useState<Record<string, MemberRunData[]>>({});
  const [metricsMap, setMetricsMap] = useState<Record<string, RunMetrics>>({});
  const currentAssistantIdRef = useRef<string | null>(null);

  // ── Right-side detail panel state ────────────────────────────
  const [selectedMember, setSelectedMember] = useState<MemberRunData | null>(null);

  const handleMemberClick = useCallback((member: MemberRunData) => {
    setSelectedMember((prev) => (prev?.id === member.id ? null : member));
  }, []);

  const handleClosePanel = useCallback(() => {
    setSelectedMember(null);
  }, []);

  // Keep side-panel member data in sync with streaming updates
  useEffect(() => {
    if (!selectedMember) return;
    const selectedId = selectedMember.id;
    for (const members of Object.values(memberRunMap)) {
      const updated: MemberRunData | undefined = members.find((m) => m.id === selectedId);
      if (updated && updated !== selectedMember) {
        setSelectedMember(updated);
        return;
      }
    }
  }, [memberRunMap, selectedMember]);

  const handleSessionId = useCallback(
    (sid: string) => {
      setSessionId(sid);
      sessionIdRef.current = sid;
      if (!hasNotifiedSessionRef.current && onSessionEstablished) {
        hasNotifiedSessionRef.current = true;
        onSessionEstablished(sid);
      }
    },
    [onSessionEstablished]
  );

  const {
    messages: agentMessages,
    sendMessage,
    status,
    error: agentError,
    stop,
  } = useChat({
    transport: new DefaultChatTransport({
      api: "/api/team-chat",
      body: () => ({
        session_id: sessionIdRef.current,
      }),
    }),
    experimental_throttle: 50,
    onFinish: ({ message }) => {
      setReasoningMap((prev) => {
        const r = prev[message.id];
        if (r && r.isActive) {
          return { ...prev, [message.id]: { ...r, isActive: false } };
        }
        return prev;
      });
      setToolCallMap((prev) => {
        const tcs = prev[message.id];
        if (tcs) {
          return {
            ...prev,
            [message.id]: tcs.map((tc) =>
              tc.status === "running" ? { ...tc, status: "completed" as const } : tc
            ),
          };
        }
        return prev;
      });
      setMemberRunMap((prev) => {
        const members = prev[message.id];
        if (members) {
          return {
            ...prev,
            [message.id]: members.map((m) =>
              m.status === "running" ? { ...m, status: "completed" as const } : m
            ),
          };
        }
        return prev;
      });
      const sessionPart = message.parts.find((p) => p.type === "data-session");
      if (sessionPart && "data" in sessionPart) {
        const data = (sessionPart as { data: { session_id?: string } }).data;
        if (data.session_id) handleSessionId(data.session_id);
      }
      currentAssistantIdRef.current = null;
    },
    onData: (dataPart) => {
      if (!dataPart || typeof dataPart !== "object") return;
      const part = dataPart as Record<string, unknown>;
      if ("session_id" in part) {
        handleSessionId(part.session_id as string);
      }
    },
    onError: (error) => {
      console.error("Agent chat error:", error);
      currentAssistantIdRef.current = null;
    },
  });

  useEffect(() => {
    if (agentMessages.length > 0) {
      const last = agentMessages[agentMessages.length - 1];
      if (last.role === "assistant") {
        currentAssistantIdRef.current = last.id;
      }
    }
  }, [agentMessages]);

  useEffect(() => {
    for (const msg of agentMessages) {
      if (msg.role !== "assistant") continue;
      for (const part of msg.parts) {
        if (part.type.startsWith("data-")) {
          const data = (part as { type: string; data: Record<string, unknown> }).data;
          switch (part.type) {
            case "data-reasoning-started": {
              const rMemberId = (data.memberId as string) || "";

              // If belongs to a member, attach reasoning to that member
              if (rMemberId) {
                setMemberRunMap((prev) => {
                  const existing = prev[msg.id] || [];
                  return {
                    ...prev,
                    [msg.id]: existing.map((m) =>
                      m.id === rMemberId
                        ? {
                            ...m,
                            reasoning: {
                              id: (data.id as string) || msg.id,
                              content: m.reasoning?.content || "",
                              isActive: true,
                            },
                          }
                        : m
                    ),
                  };
                });
              }

              setReasoningMap((prev) => ({
                ...prev,
                [msg.id]: {
                  id: (data.id as string) || msg.id,
                  content: prev[msg.id]?.content || "",
                  isActive: true,
                },
              }));
              break;
            }
            case "data-reasoning-delta": {
              const delta = (data.delta as string) || "";
              const rMemberId = (data.memberId as string) || "";

              if (rMemberId && delta) {
                setMemberRunMap((prev) => {
                  const existing = prev[msg.id] || [];
                  return {
                    ...prev,
                    [msg.id]: existing.map((m) =>
                      m.id === rMemberId
                        ? {
                            ...m,
                            reasoning: {
                              ...m.reasoning,
                              id: (data.id as string) || msg.id,
                              content: (m.reasoning?.content || "") + delta,
                              isActive: true,
                            },
                          }
                        : m
                    ),
                  };
                });
              }

              setReasoningMap((prev) => ({
                ...prev,
                [msg.id]: {
                  ...prev[msg.id],
                  id: (data.id as string) || msg.id,
                  content: (prev[msg.id]?.content || "") + delta,
                  isActive: true,
                },
              }));
              break;
            }
            case "data-reasoning-completed": {
              const rMemberId = (data.memberId as string) || "";

              if (rMemberId) {
                setMemberRunMap((prev) => {
                  const existing = prev[msg.id] || [];
                  return {
                    ...prev,
                    [msg.id]: existing.map((m) =>
                      m.id === rMemberId
                        ? {
                            ...m,
                            reasoning: {
                              ...m.reasoning,
                              id: (data.id as string) || msg.id,
                              content: m.reasoning?.content || "",
                              isActive: false,
                            },
                          }
                        : m
                    ),
                  };
                });
              }

              setReasoningMap((prev) => ({
                ...prev,
                [msg.id]: {
                  ...prev[msg.id],
                  id: (data.id as string) || msg.id,
                  content: prev[msg.id]?.content || "",
                  isActive: false,
                },
              }));
              break;
            }
            case "data-tool-call-started": {
              const tcId = (data.id as string) || "";
              const tcMemberId = (data.memberId as string) || "";

              // If this tool call belongs to a member, attach it to that member
              if (tcMemberId) {
                setMemberRunMap((prev) => {
                  const existing = prev[msg.id] || [];
                  return {
                    ...prev,
                    [msg.id]: existing.map((m) => {
                      if (m.id !== tcMemberId) return m;
                      const memberTCs = m.toolCalls || [];
                      if (memberTCs.some((tc) => tc.id === tcId)) return m;
                      return {
                        ...m,
                        toolCalls: [
                          ...memberTCs,
                          {
                            id: tcId,
                            name: (data.name as string) || "unknown",
                            args: (data.args as Record<string, unknown>) || {},
                            status: "running" as const,
                          },
                        ],
                      };
                    }),
                  };
                });
              }

              // Also track at message level
              setToolCallMap((prev) => {
                const existing = prev[msg.id] || [];
                if (existing.some((tc) => tc.id === tcId)) return prev;
                return {
                  ...prev,
                  [msg.id]: [
                    ...existing,
                    {
                      id: tcId,
                      name: (data.name as string) || "unknown",
                      args: (data.args as Record<string, unknown>) || {},
                      status: "running" as const,
                    },
                  ],
                };
              });
              break;
            }
            case "data-tool-call-completed": {
              const tcId = (data.id as string) || "";
              const tcMemberId = (data.memberId as string) || "";

              // If this tool call belongs to a member, update it there
              if (tcMemberId) {
                setMemberRunMap((prev) => {
                  const existing = prev[msg.id] || [];
                  return {
                    ...prev,
                    [msg.id]: existing.map((m) => {
                      if (m.id !== tcMemberId) return m;
                      const memberTCs = m.toolCalls || [];
                      return {
                        ...m,
                        toolCalls: memberTCs.map((tc) =>
                          tc.id === tcId
                            ? {
                                ...tc,
                                result: (data.result as string) || "",
                                error: !!(data.error),
                                status: data.error ? ("error" as const) : ("completed" as const),
                              }
                            : tc
                        ),
                      };
                    }),
                  };
                });
              }

              // Also update at message level
              setToolCallMap((prev) => {
                const existing = prev[msg.id] || [];
                return {
                  ...prev,
                  [msg.id]: existing.map((tc) =>
                    tc.id === tcId
                      ? {
                          ...tc,
                          result: (data.result as string) || "",
                          error: !!(data.error),
                          status: data.error ? ("error" as const) : ("completed" as const),
                        }
                      : tc
                  ),
                };
              });
              break;
            }
            case "data-session": {
              if (data.session_id) handleSessionId(data.session_id as string);
              break;
            }

            // ── Team member delegation events ─────────────────
            case "data-member-started": {
              const memberId = (data.id as string) || "";
              const memberName = (data.name as string) || "Agent";
              setMemberRunMap((prev) => {
                const existing = prev[msg.id] || [];
                if (existing.some((m) => m.id === memberId)) return prev;
                return {
                  ...prev,
                  [msg.id]: [
                    ...existing,
                    {
                      id: memberId,
                      name: memberName,
                      model: (data.model as string) || "",
                      status: "running" as const,
                      content: "",
                    },
                  ],
                };
              });
              break;
            }

            case "data-member-content": {
              const memberId = (data.id as string) || "";
              const delta = (data.delta as string) || "";
              if (delta) {
                setMemberRunMap((prev) => {
                  const existing = prev[msg.id] || [];
                  return {
                    ...prev,
                    [msg.id]: existing.map((m) =>
                      m.id === memberId
                        ? { ...m, content: m.content + delta }
                        : m
                    ),
                  };
                });
              }
              break;
            }

            case "data-member-completed": {
              const memberId = (data.id as string) || "";
              setMemberRunMap((prev) => {
                const existing = prev[msg.id] || [];
                return {
                  ...prev,
                  [msg.id]: existing.map((m) =>
                    m.id === memberId
                      ? {
                          ...m,
                          status: "completed" as const,
                          content: (data.content as string) || m.content,
                          input_tokens: (data.input_tokens as number) || 0,
                          output_tokens: (data.output_tokens as number) || 0,
                          total_tokens: (data.total_tokens as number) || 0,
                        }
                      : m
                  ),
                };
              });
              break;
            }

            case "data-member-error": {
              const memberId = (data.id as string) || "";
              setMemberRunMap((prev) => {
                const existing = prev[msg.id] || [];
                return {
                  ...prev,
                  [msg.id]: existing.map((m) =>
                    m.id === memberId
                      ? {
                          ...m,
                          status: "error" as const,
                          error: (data.error as string) || "Member agent error",
                        }
                      : m
                  ),
                };
              });
              break;
            }

            // ── Run metrics ───────────────────────────────────
            case "data-run-metrics": {
              setMetricsMap((prev) => ({
                ...prev,
                [msg.id]: {
                  input_tokens: (data.input_tokens as number) || 0,
                  output_tokens: (data.output_tokens as number) || 0,
                  total_tokens: (data.total_tokens as number) || 0,
                  time_to_first_token: (data.time_to_first_token as number) || undefined,
                  reasoning_tokens: (data.reasoning_tokens as number) || 0,
                },
              }));
              break;
            }
          }
        }
      }
    }
  }, [agentMessages, handleSessionId]);

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
    // Resend the last user message
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

  const { bottomRef, scrollContainerRef, showScrollBtn, handleScroll, scrollToBottom } =
    useAutoScroll([agentMessages, isAgentBusy, reasoningMap, toolCallMap, memberRunMap]);

  const renderMessages = useMemo(
    () =>
      agentMessages.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.parts
          .filter((p) => p.type === "text")
          .map((p) => (p as { text: string }).text)
          .join(""),
        streaming:
          isStreaming &&
          m.role === "assistant" &&
          m === agentMessages[agentMessages.length - 1],
        reasoning: reasoningMap[m.id],
        toolCalls: toolCallMap[m.id],
        memberRuns: memberRunMap[m.id],
        runMetrics: metricsMap[m.id],
        knowledgeData: toolCallMap[m.id]
          ? parseKnowledgeFromToolCalls(toolCallMap[m.id])
          : null,
      })),
    [agentMessages, isStreaming, reasoningMap, toolCallMap, memberRunMap, metricsMap]
  );

  const hasMessages = renderMessages.length > 0;

  return (
    <div className="relative flex h-full">
      {/* ── Chat thread area ──────────────────────────────────── */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* Messages + input unified area */}
        <ScrollArea
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1"
        >
        {!hasMessages && (
          <ChatWelcome onSuggestionClick={handleSend} />
        )}

        {/* Accessible live region for new messages */}
        <div aria-live="polite" aria-atomic="false" className="sr-only">
          {hasMessages && (
            <span>
              {renderMessages[renderMessages.length - 1].role === "assistant"
                ? "New response from FinX AI"
                : "Message sent"}
            </span>
          )}
        </div>

        {hasMessages && (
          <div className="pb-4">
            {renderMessages.map((message, index) => (
              <MemoizedMessage
                key={message.id}
                index={index}
                role={message.role}
                content={message.content}
                streaming={message.streaming}
                reasoning={message.reasoning}
                toolCalls={message.toolCalls}
                memberRuns={message.memberRuns}
                runMetrics={message.runMetrics}
                knowledgeData={message.knowledgeData}
                onSuggestionClick={handleSend}
                onMemberClick={handleMemberClick}
              />
            ))}
          </div>
        )}

        {/* Error with retry */}
        {agentError && (
          <div className="mx-auto max-w-3xl px-4 py-3 animate-message-in">
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

        {/* Loading indicator */}
        {showLoader && (
          <div className="px-4 py-5 bg-gradient-to-r from-muted/30 via-muted/10 to-transparent animate-message-in">
            <div className="mx-auto flex max-w-3xl gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20 ring-1 ring-primary/15 shadow-sm shadow-primary/5 animate-pulse-ring">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              </div>
              <div className="flex items-center gap-2.5 pt-1.5">
                <span className="text-xs font-medium text-muted-foreground/70">FinX AI is thinking</span>
                <div className="flex items-center gap-0.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/40 [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/40 [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/40" />
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} className="h-4" />

        {/* Stop generating bar — inside scroll area */}
        {isAgentBusy && (
          <div className="flex justify-center py-2">
            <button
              type="button"
              onClick={stop}
              className="flex items-center gap-1.5 rounded-full border border-border/60 bg-background/90 px-4 py-2 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur-sm transition-all hover:border-destructive/30 hover:bg-destructive/5 hover:text-destructive active:scale-95"
              aria-label="Stop generating"
            >
              <Square className="h-3 w-3" />
              Stop generating
            </button>
          </div>
        )}

        {/* Chat input — inside scroll area, unified block */}
        <div className="sticky bottom-0 z-10 border-t border-border/10 bg-background/90 px-3 py-2.5 backdrop-blur-md sm:px-4 sm:py-3">
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            isLoading={isAgentBusy}
            placeholder="Ask the FinX team anything..."
          />
        </div>
      </ScrollArea>

      {/* Scroll to bottom FAB */}
      {showScrollBtn && (
        <div className="absolute bottom-28 left-1/2 z-10 -translate-x-1/2 sm:bottom-24">
          <button
            type="button"
            onClick={scrollToBottom}
            className="flex items-center gap-1.5 rounded-full border border-border/60 bg-background/90 px-3 py-1.5 text-xs text-muted-foreground shadow-lg shadow-black/5 backdrop-blur-md transition-all hover:bg-accent hover:text-foreground hover:shadow-xl active:scale-95 animate-scale-in"
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="h-3 w-3" />
            <span className="hidden sm:inline">New messages</span>
          </button>
        </div>
      )}
      </div>

      {/* ── Right-side agent detail panel ──────────────────────── */}
      {selectedMember && (
        <div className="hidden w-[380px] shrink-0 lg:block xl:w-[420px]">
          <AgentDetailSidePanel
            member={selectedMember}
            onClose={handleClosePanel}
          />
        </div>
      )}
    </div>
  );
}

// ── Memoized message wrapper (avoids re-rendering unchanged messages) ──
interface MemoizedMessageProps {
  index: number;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  reasoning?: ReasoningData;
  toolCalls?: ToolCallData[];
  memberRuns?: MemberRunData[];
  runMetrics?: RunMetrics;
  knowledgeData?: import("./knowledge-panel").KnowledgeData | null;
  onSuggestionClick: (text: string) => void;
  onMemberClick?: (member: MemberRunData) => void;
}

const MemoizedMessage = memo(function MemoizedMessage({
  index,
  role,
  content,
  streaming,
  reasoning,
  toolCalls,
  memberRuns,
  runMetrics,
  knowledgeData,
  onSuggestionClick,
  onMemberClick,
}: MemoizedMessageProps) {
  return (
    <div
      className="animate-message-in"
      style={{ animationDelay: `${Math.min(index * 30, 150)}ms` }}
    >
      <ChatMessage
        role={role}
        content={content}
        streaming={streaming}
        reasoning={reasoning}
        toolCalls={toolCalls}
        memberRuns={memberRuns}
        runMetrics={runMetrics}
        knowledgeData={knowledgeData}
        onSuggestionClick={onSuggestionClick}
        onMemberClick={onMemberClick}
      />
    </div>
  );
});
