import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";
import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

export const maxDuration = 180;

// Known tool names used by the company-knowledge agent for knowledge retrieval
const KNOWLEDGE_SEARCH_TOOLS = new Set(["search_knowledge", "search_knowledge_base", "retrieve_documents"]);

/**
 * Parse a tagged JSON block from content.
 * Supports both `<citations>` (post-hook) and `<retrieval-citations>` (streaming).
 */
function extractTaggedBlock(
  content: string,
  tag: string
): { items: Array<Record<string, unknown>>; cleaned: string } {
  const openTag = `<${tag}>`;
  const closeTag = `</${tag}>`;
  const tagStart = content.lastIndexOf(openTag);
  const tagEnd = content.lastIndexOf(closeTag);
  if (tagStart === -1 || tagEnd === -1 || tagEnd < tagStart) {
    return { items: [], cleaned: content };
  }

  const jsonStr = content.slice(tagStart + openTag.length, tagEnd);
  let items: Array<Record<string, unknown>> = [];
  try {
    const parsed = JSON.parse(jsonStr);
    if (Array.isArray(parsed)) items = parsed;
  } catch {
    // Malformed block — ignore but still clean up the tag
  }

  const cleaned = content.slice(0, tagStart).trimEnd();
  return { items, cleaned };
}

/** Backward-compatible wrapper for the post-hook <citations> block */
function extractCitationsBlock(content: string): {
  citations: Array<Record<string, unknown>>;
  cleanedContent: string;
} {
  const { items, cleaned } = extractTaggedBlock(content, "citations");
  return { citations: items, cleanedContent: cleaned };
}

/** Parse <retrieval-citations> block embedded in tool call results (streaming) */
function extractRetrievalCitations(resultStr: string): Array<Record<string, unknown>> {
  const { items } = extractTaggedBlock(resultStr, "retrieval-citations");
  return items;
}

/** Emit a single citation as a data-citation-added event */
function writeCitationEvent(
  writer: Parameters<Parameters<typeof createUIMessageStream>[0]["execute"]>[0]["writer"],
  citation: Record<string, unknown>,
  emittedIds: Set<string>
) {
  const id = (citation.id as string) || crypto.randomUUID();
  if (emittedIds.has(id)) return;
  emittedIds.add(id);

  writer.write({
    type: "data-citation-added" as `data-${string}`,
    data: {
      id,
      title: (citation.title as string) || "",
      sourceType: (citation.source_type as string) || "unknown",
      snippet: (citation.snippet as string) || "",
      content: (citation.content as string) || "",
      page: citation.page ?? undefined,
      url: (citation.url as string) || undefined,
      score: typeof citation.score === "number" ? citation.score : undefined,
      index: typeof citation.index === "number" ? citation.index : undefined,
      // Artifact metadata
      artifactUri: (citation.artifact_uri as string) || undefined,
      mimeType: (citation.mime_type as string) || undefined,
      isArtifact: citation.is_artifact === true ? true : undefined,
      artifactType: (citation.artifact_type as string) || undefined,
      // Parent Confluence page context
      parentContentId: (citation.parent_content_id as string) || undefined,
      parentTitle: (citation.parent_title as string) || undefined,
      parentUrl: (citation.parent_url as string) || undefined,
      spaceKey: (citation.space_key as string) || undefined,
      // Source classification
      contentSourceType: (citation.content_source_type as string) || (citation.source_type_raw as string) || undefined,
      chunkKind: (citation.chunk_kind as string) || undefined,
    },
  });
}

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
        // Track emitted citation IDs to deduplicate between streaming
        // (ToolCallCompleted) and final (RunCompleted) emission.
        const emittedCitationIds = new Set<string>();

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

                  // Emit activity status for knowledge search tools
                  if (KNOWLEDGE_SEARCH_TOOLS.has(toolName)) {
                    const toolArgs = (tool?.tool_args as Record<string, unknown>) || {};
                    const query = (toolArgs.query as string) || (toolArgs.q as string) || "";
                    writer.write({
                      type: "data-activity" as `data-${string}`,
                      data: {
                        status: "searching",
                        query,
                        timestamp: Date.now(),
                      },
                    });
                  }

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

                  if (KNOWLEDGE_SEARCH_TOOLS.has(toolName)) {
                    // Extract streaming citations from the retrieval result
                    const streamCitations = extractRetrievalCitations(resultStr);

                    // Emit "reading N sources" activity
                    if (streamCitations.length > 0) {
                      writer.write({
                        type: "data-activity" as `data-${string}`,
                        data: {
                          status: "reading",
                          count: streamCitations.length,
                          timestamp: Date.now(),
                        },
                      });

                      // Emit each citation immediately (streaming)
                      for (const citation of streamCitations) {
                        writeCitationEvent(writer, citation, emittedCitationIds);
                      }
                    }

                    // Transition to "drafting" — LLM will start generating now
                    writer.write({
                      type: "data-activity" as `data-${string}`,
                      data: { status: "drafting", timestamp: Date.now() },
                    });
                  }

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

                  if (KNOWLEDGE_SEARCH_TOOLS.has(toolName)) {
                    writer.write({
                      type: "data-activity" as `data-${string}`,
                      data: { status: "done", timestamp: Date.now() },
                    });
                  }

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
                  const rawContent = (parsed.content as string) || "";

                  // Extract citations block before deciding what text to emit
                  const { citations, cleanedContent } = extractCitationsBlock(rawContent);

                  // If text wasn't already streamed during RunContent events,
                  // emit the cleaned content now (before closing the text part)
                  if (!textStarted && cleanedContent) {
                    const trimmed = cleanedContent.trim();
                    if (trimmed) {
                      writer.write({ type: "text-start", id: textPartId });
                      textStarted = true;
                      const chunks = trimmed.split(/(\n\n)/);
                      for (const chunk of chunks) {
                        if (chunk) {
                          writer.write({ type: "text-delta", id: textPartId, delta: chunk });
                        }
                      }
                    }
                  }

                  // Emit citations BEFORE text-end so they land in the same message.
                  // Uses dedup set — citations already emitted during streaming
                  // (via ToolCallCompleted) will be skipped here.
                  for (const citation of citations) {
                    writeCitationEvent(writer, citation, emittedCitationIds);
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
