"use client";

/**
 * use-chat-data-parts
 *
 * Processes the custom `data-*` message parts emitted by the Agno backend
 * (reasoning, tool calls, member delegation, metrics, session id, citations,
 * activity status) and accumulates them into separate state maps.
 *
 * Extracted from chat-container.tsx so that component stays focused on
 * layout and interaction logic.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import type { UIMessage } from "ai";
import type {
  ToolCallData,
  ReasoningData,
  MemberRunData,
  RunMetrics,
  CitationData,
  ActivityData,
} from "@/types";

interface UseChatDataPartsOptions {
  onSessionId?: (sessionId: string) => void;
}

export interface ChatDataMaps {
  reasoningMap: Record<string, ReasoningData>;
  toolCallMap: Record<string, ToolCallData[]>;
  memberRunMap: Record<string, MemberRunData[]>;
  metricsMap: Record<string, RunMetrics>;
  citationsMap: Record<string, CitationData[]>;
  activityMap: Record<string, ActivityData>;
  /** Call in useChat onFinish to close any still-running states */
  markRunsComplete: (messageId: string) => void;
}

export function useChatDataParts(
  messages: UIMessage[],
  { onSessionId }: UseChatDataPartsOptions = {}
): ChatDataMaps {
  const [reasoningMap, setReasoningMap] = useState<Record<string, ReasoningData>>({});
  const [toolCallMap, setToolCallMap] = useState<Record<string, ToolCallData[]>>({});
  const [memberRunMap, setMemberRunMap] = useState<Record<string, MemberRunData[]>>({});
  const [metricsMap, setMetricsMap] = useState<Record<string, RunMetrics>>({});
  const [citationsMap, setCitationsMap] = useState<Record<string, CitationData[]>>({});
  const [activityMap, setActivityMap] = useState<Record<string, ActivityData>>({});

  // Track the ID of the currently-streaming assistant message to avoid
  // scanning the entire list on every token.
  const currentAssistantIdRef = useRef<string | null>(null);

  // Each processed part is keyed `msgId::partIndex::partType` to prevent
  // double-processing when the message list re-renders without new parts.
  const processedPartsRef = useRef(new Set<string>());

  const onSessionIdRef = useRef(onSessionId);
  onSessionIdRef.current = onSessionId;

  // Keep currentAssistantIdRef in sync with the latest streaming message.
  useEffect(() => {
    if (messages.length === 0) return;
    const last = messages[messages.length - 1];
    if (last.role === "assistant") {
      currentAssistantIdRef.current = last.id;
    }
  }, [messages]);

  // Main scanning effect — only the current assistant message is scanned
  // after the initial pass, making this O(1) per token during streaming.
  useEffect(() => {
    const lastAssistantId = currentAssistantIdRef.current;
    const toScan = lastAssistantId
      ? messages.filter((m) => m.id === lastAssistantId)
      : messages.filter((m) => m.role === "assistant");

    const processed = processedPartsRef.current;

    for (const msg of toScan) {
      if (msg.role !== "assistant") continue;
      for (let i = 0; i < msg.parts.length; i++) {
        const part = msg.parts[i];
        if (!part.type.startsWith("data-")) continue;

        const key = `${msg.id}::${i}::${part.type}`;
        if (processed.has(key)) continue;
        processed.add(key);

        const data = (part as { type: string; data: Record<string, unknown> }).data;

        switch (part.type) {
          // ── Reasoning ─────────────────────────────────────
          case "data-reasoning-started": {
            const rMid = (data.memberId as string) || "";
            if (rMid) {
              setMemberRunMap((p) => ({
                ...p,
                [msg.id]: (p[msg.id] || []).map((m) =>
                  m.id === rMid
                    ? { ...m, reasoning: { id: (data.id as string) || msg.id, content: m.reasoning?.content || "", isActive: true } }
                    : m
                ),
              }));
            }
            setReasoningMap((p) => ({
              ...p,
              [msg.id]: { id: (data.id as string) || msg.id, content: p[msg.id]?.content || "", isActive: true },
            }));
            break;
          }
          case "data-reasoning-delta": {
            const delta = (data.delta as string) || "";
            const rMid = (data.memberId as string) || "";
            if (rMid && delta) {
              setMemberRunMap((p) => ({
                ...p,
                [msg.id]: (p[msg.id] || []).map((m) =>
                  m.id === rMid
                    ? { ...m, reasoning: { ...m.reasoning, id: (data.id as string) || msg.id, content: (m.reasoning?.content || "") + delta, isActive: true } }
                    : m
                ),
              }));
            }
            setReasoningMap((p) => ({
              ...p,
              [msg.id]: { ...p[msg.id], id: (data.id as string) || msg.id, content: (p[msg.id]?.content || "") + delta, isActive: true },
            }));
            break;
          }
          case "data-reasoning-completed": {
            const rMid = (data.memberId as string) || "";
            if (rMid) {
              setMemberRunMap((p) => ({
                ...p,
                [msg.id]: (p[msg.id] || []).map((m) =>
                  m.id === rMid
                    ? { ...m, reasoning: { ...m.reasoning, id: (data.id as string) || msg.id, content: m.reasoning?.content || "", isActive: false } }
                    : m
                ),
              }));
            }
            setReasoningMap((p) => ({
              ...p,
              [msg.id]: { ...p[msg.id], id: (data.id as string) || msg.id, content: p[msg.id]?.content || "", isActive: false },
            }));
            break;
          }

          // ── Tool calls ───────────────────────────────────
          case "data-tool-call-started": {
            const tcId = (data.id as string) || "";
            const tcMid = (data.memberId as string) || "";
            const newTC: ToolCallData = {
              id: tcId,
              name: (data.name as string) || "unknown",
              args: (data.args as Record<string, unknown>) || {},
              status: "running",
            };
            if (tcMid) {
              setMemberRunMap((p) => ({
                ...p,
                [msg.id]: (p[msg.id] || []).map((m) => {
                  if (m.id !== tcMid) return m;
                  const tcs = m.toolCalls || [];
                  return tcs.some((tc) => tc.id === tcId) ? m : { ...m, toolCalls: [...tcs, newTC] };
                }),
              }));
            }
            setToolCallMap((p) => {
              const ex = p[msg.id] || [];
              return ex.some((tc) => tc.id === tcId) ? p : { ...p, [msg.id]: [...ex, newTC] };
            });
            break;
          }
          case "data-tool-call-completed": {
            const tcId = (data.id as string) || "";
            const tcMid = (data.memberId as string) || "";
            const patch = {
              result: (data.result as string) || "",
              error: !!(data.error),
              status: data.error ? ("error" as const) : ("completed" as const),
            };
            if (tcMid) {
              setMemberRunMap((p) => ({
                ...p,
                [msg.id]: (p[msg.id] || []).map((m) =>
                  m.id !== tcMid
                    ? m
                    : { ...m, toolCalls: (m.toolCalls || []).map((tc) => tc.id === tcId ? { ...tc, ...patch } : tc) }
                ),
              }));
            }
            setToolCallMap((p) => ({
              ...p,
              [msg.id]: (p[msg.id] || []).map((tc) => tc.id === tcId ? { ...tc, ...patch } : tc),
            }));
            break;
          }

          // ── Session id ────────────────────────────────────
          case "data-session": {
            if (data.session_id) onSessionIdRef.current?.(data.session_id as string);
            break;
          }

          // ── Team member delegation ────────────────────────
          case "data-member-started": {
            const mid = (data.id as string) || "";
            setMemberRunMap((p) => {
              const ex = p[msg.id] || [];
              if (ex.some((m) => m.id === mid)) return p;
              return {
                ...p,
                [msg.id]: [
                  ...ex,
                  { id: mid, name: (data.name as string) || "Agent", model: (data.model as string) || "", status: "running" as const, content: "" },
                ],
              };
            });
            break;
          }
          case "data-member-content": {
            const mid = (data.id as string) || "";
            const delta = (data.delta as string) || "";
            if (delta) {
              setMemberRunMap((p) => ({
                ...p,
                [msg.id]: (p[msg.id] || []).map((m) => m.id === mid ? { ...m, content: m.content + delta } : m),
              }));
            }
            break;
          }
          case "data-member-completed": {
            const mid = (data.id as string) || "";
            setMemberRunMap((p) => ({
              ...p,
              [msg.id]: (p[msg.id] || []).map((m) =>
                m.id !== mid ? m : {
                  ...m,
                  status: "completed" as const,
                  content: (data.content as string) || m.content,
                  input_tokens: (data.input_tokens as number) || 0,
                  output_tokens: (data.output_tokens as number) || 0,
                  total_tokens: (data.total_tokens as number) || 0,
                }
              ),
            }));
            break;
          }
          case "data-member-error": {
            const mid = (data.id as string) || "";
            setMemberRunMap((p) => ({
              ...p,
              [msg.id]: (p[msg.id] || []).map((m) =>
                m.id !== mid ? m : { ...m, status: "error" as const, error: (data.error as string) || "Member agent error" }
              ),
            }));
            break;
          }

          // ── Run metrics ───────────────────────────────────
          case "data-run-metrics": {
            setMetricsMap((p) => ({
              ...p,
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

          // ── Citations ─────────────────────────────────────
          case "data-citation-added": {
            const citation: CitationData = {
              id: (data.id as string) || crypto.randomUUID(),
              title: (data.title as string) || "",
              sourceType: (data.sourceType as CitationData["sourceType"]) || "unknown",
              snippet: (data.snippet as string) || "",
              content: (data.content as string) || undefined,
              page: data.page as number | string | undefined,
              url: (data.url as string) || undefined,
              score: typeof data.score === "number" ? data.score : undefined,
              index: typeof data.index === "number" ? data.index : undefined,
              // Artifact metadata
              artifactUri: (data.artifactUri as string) || undefined,
              mimeType: (data.mimeType as string) || undefined,
              isArtifact: data.isArtifact === true ? true : undefined,
              artifactType: (data.artifactType as CitationData["artifactType"]) || undefined,
              // Parent Confluence page context
              parentContentId: (data.parentContentId as string) || undefined,
              parentTitle: (data.parentTitle as string) || undefined,
              parentUrl: (data.parentUrl as string) || undefined,
              spaceKey: (data.spaceKey as string) || undefined,
              // Source classification
              contentSourceType: (data.contentSourceType as string) || undefined,
              chunkKind: (data.chunkKind as string) || undefined,
            };
            setCitationsMap((p) => {
              const ex = p[msg.id] || [];
              // Deduplicate by id
              if (ex.some((c) => c.id === citation.id)) return p;
              return { ...p, [msg.id]: [...ex, citation] };
            });
            break;
          }

          // ── Activity status ───────────────────────────────
          case "data-activity": {
            const activity: ActivityData = {
              status: (data.status as ActivityData["status"]) || "idle",
              query: (data.query as string) || undefined,
              count: typeof data.count === "number" ? data.count : undefined,
              timestamp: (data.timestamp as number) || Date.now(),
            };
            setActivityMap((p) => ({ ...p, [msg.id]: activity }));
            break;
          }
        }
      }
    }
    // messages is the only dep we need — all setters are stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  const markRunsComplete = useCallback((messageId: string) => {
    setReasoningMap((p) => {
      const r = p[messageId];
      return r?.isActive ? { ...p, [messageId]: { ...r, isActive: false } } : p;
    });
    setToolCallMap((p) => {
      const tcs = p[messageId];
      if (!tcs) return p;
      return { ...p, [messageId]: tcs.map((tc) => tc.status === "running" ? { ...tc, status: "completed" as const } : tc) };
    });
    setMemberRunMap((p) => {
      const ms = p[messageId];
      if (!ms) return p;
      return { ...p, [messageId]: ms.map((m) => m.status === "running" ? { ...m, status: "completed" as const } : m) };
    });
    // Mark activity as idle when run completes
    setActivityMap((p) => {
      const a = p[messageId];
      if (!a || a.status === "idle" || a.status === "done") return p;
      return { ...p, [messageId]: { ...a, status: "done" } };
    });
  }, []);

  return { reasoningMap, toolCallMap, memberRunMap, metricsMap, citationsMap, activityMap, markRunsComplete };
}
