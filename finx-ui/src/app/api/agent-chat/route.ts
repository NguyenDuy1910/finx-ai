import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";
import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

export const maxDuration = 180;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (!body.messages && !body.message) {
      return NextResponse.json(
        { error: "messages or message is required" },
        { status: 400 }
      );
    }

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

    const agentId = body.agent_id || "confluence-researcher";

    const formData = new URLSearchParams();
    formData.append("message", userMessage);
    formData.append("stream", "true");
    formData.append("stream_events", "true");
    formData.append("user_id", body.user_id || "finx-ui-user");
    if (body.session_id) {
      formData.append("session_id", body.session_id);
    }

    const upstream = await fetchFromBackend(
      `/agents/${agentId}/runs`,
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
        timeout: 180_000,
      }
    );

    if (!upstream.ok) {
      const detail = await upstream.text().catch(() => "Backend error");
      return NextResponse.json({ error: detail }, { status: upstream.status });
    }

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
                case "RunStarted": {
                  writer.write({
                    type: "data-run-started" as `data-${string}`,
                    data: {
                      model: parsed.model || "",
                      model_provider: parsed.model_provider || "",
                      session_id: parsed.session_id || null,
                      agent_name: (parsed.agent_name as string) || "",
                    },
                  });
                  break;
                }

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
                  const stepContent =
                    (parsed.reasoning_content as string) ||
                    (parsed.content as string) || "";
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

                case "ToolCallStarted": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const toolName = (tool?.tool_name as string) || "unknown";
                  toolCallCounter++;
                  const tcId = (tool?.tool_call_id as string) || `tc-${toolCallCounter}`;
                  writer.write({
                    type: "data-tool-call-started" as `data-${string}`,
                    data: {
                      id: tcId,
                      name: toolName,
                      args: tool?.tool_args || {},
                    },
                  });
                  break;
                }

                case "ToolCallCompleted": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const toolName = (tool?.tool_name as string) || "unknown";
                  const resultStr = (tool?.result as string) || "";
                  const tcId = (tool?.tool_call_id as string) || `tc-${toolCallCounter}`;
                  writer.write({
                    type: "data-tool-call-completed" as `data-${string}`,
                    data: {
                      id: tcId,
                      name: toolName,
                      result: resultStr,
                      error: tool?.tool_call_error || false,
                    },
                  });
                  break;
                }

                case "ToolCallError": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const toolName = (tool?.tool_name as string) || "unknown";
                  const tcId = (tool?.tool_call_id as string) || `tc-${toolCallCounter}`;
                  writer.write({
                    type: "data-tool-call-completed" as `data-${string}`,
                    data: {
                      id: tcId,
                      name: toolName,
                      result: (parsed.error as string) || "Tool call failed",
                      error: true,
                    },
                  });
                  break;
                }

                case "RunContent": {
                  const content = (parsed.content as string) || "";
                  if (content) {
                    if (!textStarted) {
                      writer.write({ type: "text-start", id: textPartId });
                      textStarted = true;
                    }
                    writer.write({
                      type: "text-delta",
                      id: textPartId,
                      delta: content,
                    });
                  }

                  if (parsed.reasoning_content && reasoningStarted) {
                    writer.write({
                      type: "data-reasoning-delta" as `data-${string}`,
                      data: {
                        id: reasoningPartId,
                        delta: parsed.reasoning_content as string,
                      },
                    });
                  }
                  break;
                }

                case "RunCompleted": {
                  if (!textStarted && parsed.content) {
                    const content = (parsed.content as string).trim();
                    if (content) {
                      writer.write({ type: "text-start", id: textPartId });
                      textStarted = true;
                      const chunks = content.split(/(\n\n)/);
                      for (const chunk of chunks) {
                        if (chunk) {
                          writer.write({ type: "text-delta", id: textPartId, delta: chunk });
                        }
                      }
                    }
                  }

                  if (parsed.session_id) {
                    writer.write({
                      type: "data-session" as `data-${string}`,
                      data: { session_id: parsed.session_id },
                    });
                  }
                  if (parsed.metrics) {
                    writer.write({
                      type: "data-run-metrics" as `data-${string}`,
                      data: parsed.metrics,
                    });
                  }
                  break;
                }

                case "RunError": {
                  writer.write({
                    type: "error",
                    errorText: (parsed.content as string) || (parsed.error as string) || "An error occurred",
                  });
                  break;
                }

                case "ModelRequestStarted":
                case "ModelRequestCompleted": {
                  break;
                }

                default: {
                  if (parsed.content && typeof parsed.content === "string") {
                    const content = parsed.content.trim();
                    if (content) {
                      if (!textStarted) {
                        writer.write({ type: "text-start", id: textPartId });
                        textStarted = true;
                      }
                      writer.write({
                        type: "text-delta",
                        id: textPartId,
                        delta: content,
                      });
                    }
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
