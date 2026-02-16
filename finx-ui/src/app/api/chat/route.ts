import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";
import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

export const maxDuration = 120;

/**
 * Converts Agno AgentOS SSE events into Vercel AI SDK UI Message Stream protocol.
 *
 * AgentOS SSE events we handle:
 *   RunStarted           → session / model info
 *   RunContent            → content deltas (token-by-token)
 *   RunCompleted          → final content, metrics, session_id
 *   ReasoningStarted      → thinking begins
 *   ReasoningContentDelta → thinking tokens
 *   ReasoningStep         → reasoning step content
 *   ReasoningCompleted    → thinking ends
 *   ToolCallStarted       → tool invocation begins
 *   ToolCallCompleted     → tool result arrives
 *   ToolCallError         → tool error
 *
 * All non-text events are forwarded as `data-*` parts so the UI can
 * render thinking indicators, tool call cards, etc.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (!body.messages && !body.message) {
      return NextResponse.json(
        { error: "messages or message is required" },
        { status: 400 }
      );
    }

    // ─── Agent mode (Vercel AI SDK ↔ AgentOS bridge) ──────────────
    let userMessage = body.message || "";
    if (!userMessage && Array.isArray(body.messages) && body.messages.length > 0) {
      const lastMsg = body.messages[body.messages.length - 1];
      if (lastMsg.parts) {
        const textPart = lastMsg.parts.find(
          (p: { type: string }) => p.type === "text"
        );
        userMessage = textPart?.text || lastMsg.content || "";
      } else {
        userMessage = lastMsg.content || "";
      }
    }

    if (!userMessage) {
      return NextResponse.json(
        { error: "No user message found" },
        { status: 400 }
      );
    }

    // Call AgentOS native endpoint
    const formData = new URLSearchParams();
    formData.append("message", userMessage);
    formData.append("stream", "true");
    formData.append("stream_events", "true");
    formData.append("user_id", body.user_id || "finx-ui-user");
    if (body.session_id) {
      formData.append("session_id", body.session_id);
    }

    const upstream = await fetchFromBackend(
      "/agents/knowledge-agent/runs",
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
        timeout: 120_000,
      }
    );

    if (!upstream.ok) {
      const detail = await upstream.text().catch(() => "Backend error");
      return NextResponse.json({ error: detail }, { status: upstream.status });
    }

    // Convert AgentOS SSE → Vercel AI SDK UI Message Stream
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        const reader = upstream.body?.getReader();
        if (!reader) {
          writer.write({ type: "error", errorText: "No response body from agent" });
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "";
        const textPartId = crypto.randomUUID();
        let textStarted = false;

        // Counters for unique IDs
        let reasoningPartId = "";
        let reasoningStarted = false;
        let toolCallCounter = 0;

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              const trimmed = line.trim();

              if (trimmed.startsWith("event:")) {
                currentEvent = trimmed.slice(6).trim();
                continue;
              }

              if (!trimmed.startsWith("data:")) continue;
              const payload = trimmed.slice(5).trim();
              if (!payload || payload === "[DONE]") continue;

              let parsed: Record<string, unknown>;
              try {
                parsed = JSON.parse(payload);
              } catch {
                currentEvent = "";
                continue;
              }

              switch (currentEvent) {
                // ── Run lifecycle ──────────────────────────────
                case "RunStarted": {
                  writer.write({
                    type: "data-run-started" as `data-${string}`,
                    data: {
                      model: parsed.model || "",
                      model_provider: parsed.model_provider || "",
                      session_id: parsed.session_id || null,
                      agent_name: parsed.agent_name || "",
                    },
                  });
                  break;
                }

                // ── Reasoning / Thinking ──────────────────────
                case "ReasoningStarted": {
                  reasoningPartId = crypto.randomUUID();
                  reasoningStarted = true;
                  writer.write({
                    type: "data-reasoning-started" as `data-${string}`,
                    data: { id: reasoningPartId },
                  });
                  break;
                }

                case "ReasoningContentDelta": {
                  const delta = (parsed.reasoning_content as string) || "";
                  if (delta) {
                    writer.write({
                      type: "data-reasoning-delta" as `data-${string}`,
                      data: { id: reasoningPartId, delta },
                    });
                  }
                  break;
                }

                case "ReasoningStep": {
                  const stepContent = (parsed.reasoning_content as string) || (parsed.content as string) || "";
                  if (stepContent) {
                    writer.write({
                      type: "data-reasoning-delta" as `data-${string}`,
                      data: { id: reasoningPartId, delta: stepContent },
                    });
                  }
                  break;
                }

                case "ReasoningCompleted": {
                  if (reasoningStarted) {
                    writer.write({
                      type: "data-reasoning-completed" as `data-${string}`,
                      data: { id: reasoningPartId },
                    });
                    reasoningStarted = false;
                  }
                  break;
                }

                // ── Tool calls ────────────────────────────────
                case "ToolCallStarted": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  toolCallCounter++;
                  writer.write({
                    type: "data-tool-call-started" as `data-${string}`,
                    data: {
                      id: (tool?.tool_call_id as string) || `tc-${toolCallCounter}`,
                      name: (tool?.tool_name as string) || "unknown",
                      args: tool?.tool_args || {},
                    },
                  });
                  break;
                }

                case "ToolCallCompleted": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const resultStr = (tool?.result as string) || (parsed.content as string) || "";
                  writer.write({
                    type: "data-tool-call-completed" as `data-${string}`,
                    data: {
                      id: (tool?.tool_call_id as string) || `tc-${toolCallCounter}`,
                      name: (tool?.tool_name as string) || "unknown",
                      result: resultStr,
                      error: tool?.tool_call_error || false,
                    },
                  });
                  break;
                }

                case "ToolCallError": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  writer.write({
                    type: "data-tool-call-completed" as `data-${string}`,
                    data: {
                      id: (tool?.tool_call_id as string) || `tc-${toolCallCounter}`,
                      name: (tool?.tool_name as string) || "unknown",
                      result: (parsed.error as string) || "Tool call failed",
                      error: true,
                    },
                  });
                  break;
                }

                // ── Content tokens ────────────────────────────
                case "RunContent": {
                  if (!textStarted) {
                    writer.write({ type: "text-start", id: textPartId });
                    textStarted = true;
                  }
                  if (parsed.content) {
                    writer.write({
                      type: "text-delta",
                      id: textPartId,
                      delta: parsed.content as string,
                    });
                  }
                  // RunContent can also carry reasoning_content
                  if (parsed.reasoning_content && reasoningStarted) {
                    writer.write({
                      type: "data-reasoning-delta" as `data-${string}`,
                      data: { id: reasoningPartId, delta: parsed.reasoning_content as string },
                    });
                  }
                  break;
                }

                // ── Run completed ─────────────────────────────
                case "RunCompleted": {
                  if (!textStarted && parsed.content) {
                    writer.write({ type: "text-start", id: textPartId });
                    writer.write({
                      type: "text-delta",
                      id: textPartId,
                      delta: parsed.content as string,
                    });
                    textStarted = true;
                  }

                  if (parsed.session_id) {
                    writer.write({
                      type: "data-session" as `data-${string}`,
                      data: { session_id: parsed.session_id },
                    });
                  }
                  if (parsed.metrics) {
                    writer.write({
                      type: "data-metrics" as `data-${string}`,
                      data: parsed.metrics,
                    });
                  }
                  break;
                }

                // ── Error ─────────────────────────────────────
                case "RunError": {
                  writer.write({
                    type: "error",
                    errorText: (parsed.content as string) || "An error occurred",
                  });
                  break;
                }

                // ── Fallback: content from unknown event ──────
                default: {
                  if (parsed.content && typeof parsed.content === "string") {
                    if (!textStarted) {
                      writer.write({ type: "text-start", id: textPartId });
                      textStarted = true;
                    }
                    writer.write({
                      type: "text-delta",
                      id: textPartId,
                      delta: parsed.content,
                    });
                  }
                  break;
                }
              }

              currentEvent = "";
            }
          }
        } finally {
          reader.releaseLock();
        }

        if (textStarted) {
          writer.write({ type: "text-end", id: textPartId });
        }
      },
    });

    return createUIMessageStreamResponse({
      stream,
      headers: {
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        { error: error.detail },
        { status: error.status }
      );
    }
    const message =
      error instanceof Error && error.name === "AbortError"
        ? "Backend request timed out"
        : "Failed to connect to backend";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
