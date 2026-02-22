import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";
import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

export const maxDuration = 180;

/**
 * Converts Agno AgentOS **Team** SSE events into Vercel AI SDK UI Message Stream.
 *
 * Team-specific events on top of single-agent events:
 *   TeamRunStarted         → team run begins
 *   TeamRunContent         → team coordinator content
 *   TeamRunCompleted       → team run ends with full metrics
 *   MemberRunStarted       → member agent delegation begins
 *   MemberRunContent       → member agent content deltas
 *   MemberRunCompleted     → member agent run ends
 *   MemberRunError         → member agent error
 *
 * Single-agent events (also emitted by members):
 *   RunStarted / RunContent / RunCompleted / RunError
 *   ReasoningStarted / ReasoningContentDelta / ReasoningStep / ReasoningCompleted
 *   ToolCallStarted / ToolCallCompleted / ToolCallError
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

    // Extract user message
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

    // Call AgentOS team endpoint
    const formData = new URLSearchParams();
    formData.append("message", userMessage);
    formData.append("stream", "true");
    formData.append("stream_events", "true");
    formData.append("user_id", body.user_id || "finx-ui-user");
    if (body.session_id) {
      formData.append("session_id", body.session_id);
    }

    const upstream = await fetchFromBackend(
      "/teams/finx-team/runs",
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

    // Convert AgentOS Team SSE → Vercel AI SDK UI Message Stream
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        const reader = upstream.body?.getReader();
        if (!reader) {
          writer.write({ type: "error", errorText: "No response body from team" });
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "";
        const textPartId = crypto.randomUUID();
        let textStarted = false;

        // Tracking state
        let reasoningPartId = "";
        let reasoningStarted = false;
        let toolCallCounter = 0;
        let memberCounter = 0;
        let activeMemberId = "";  // Track currently running member
        let pendingMemberDelegation = "";  // Track pending member name from delegate_task_to_member

        // ── Agno framework noise filters ──────────────────
        // Agno injects internal function-call strings into the content
        // stream (e.g. "delegate_task_to_member(...) completed in 0.01s.")
        // These must be stripped so they don't show up in the chat UI.
        const NOISE_PATTERNS = [
          /delegate_task_to_members?\s*\(.*?\)\s*completed\s+in\s+[\d.]+s\.\s*/gi,
          /delegate_task_to_members?\s*\(.*?\)\s*/gi,
          /transfer_task_to_members?\s*\(.*?\)\s*completed\s+in\s+[\d.]+s\.\s*/gi,
          /transfer_task_to_members?\s*\(.*?\)\s*/gi,
          // Only match known Agno internal function call logs — avoid stripping user content
          /(?:run_team|execute_workflow|process_request|get_response)\s*\(.*?\)\s*completed\s+in\s+[\d.]+s\.\s*/gi,
        ];

        function isFrameworkNoise(text: string): boolean {
          const trimmed = text.trim();
          if (!trimmed) return true;
          // Check if entire string is just a framework call log
          if (/^[\w_]+\(.*\)\s*completed\s+in\s+[\d.]+s\.?\s*$/i.test(trimmed)) return true;
          if (/^[\w_]+\(.*\)\s*$/i.test(trimmed) && /delegate_task|transfer_task/i.test(trimmed)) return true;
          return false;
        }

        function stripFrameworkNoise(text: string): string {
          let cleaned = text;
          for (const pattern of NOISE_PATTERNS) {
            // Reset lastIndex for global regex
            pattern.lastIndex = 0;
            cleaned = cleaned.replace(pattern, "");
          }
          return cleaned;
        }

        /**
         * Clean up the final coordinator summary so it renders nicely
         * in markdown. Agno sometimes sends content with:
         *  - stacked blank lines (3+)
         *  - trailing whitespace
         *  - leading/trailing newlines
         *  - duplicated section headers
         *  - raw agent output noise mixed in
         */
        function cleanFinalContent(raw: string): string {
          let cleaned = raw
            .replace(/\n{3,}/g, "\n\n")   // collapse 3+ newlines → 2
            .replace(/[ \t]+$/gm, "")       // strip trailing whitespace per line
            .trim();

          // Remove duplicated consecutive lines (Agno sometimes duplicates headers)
          const lines = cleaned.split("\n");
          const deduped: string[] = [];
          for (let i = 0; i < lines.length; i++) {
            const trimmedLine = lines[i].trim();
            if (i > 0 && trimmedLine && trimmedLine === lines[i - 1]?.trim()) {
              continue; // skip duplicate
            }
            deduped.push(lines[i]);
          }
          cleaned = deduped.join("\n");

          // Ensure section headers have proper spacing
          cleaned = cleaned
            .replace(/(#{1,3}\s)/g, "\n$1")   // ensure newline before headers
            .replace(/\n{3,}/g, "\n\n")        // re-collapse after header fix
            .trim();

          return cleaned;
        }

        /**
         * Emit final content in small chunks so the UI shows a smooth
         * streaming animation rather than a single wall-of-text flash.
         * Chunks on paragraph boundaries when possible.
         */
        function emitFinalContent(
          w: typeof writer,
          partId: string,
          content: string,
        ) {
          const clean = cleanFinalContent(stripFrameworkNoise(content));
          if (!clean || isFrameworkNoise(clean)) return false;

          w.write({ type: "text-start", id: partId });

          // Split into paragraph-level chunks for progressive rendering
          const chunks = clean.split(/(\n\n)/);
          for (const chunk of chunks) {
            if (chunk) {
              w.write({ type: "text-delta", id: partId, delta: chunk });
            }
          }
          return true;
        }

        function isInternalToolCall(name: string): boolean {
          const lower = name.toLowerCase();
          return (
            lower === "delegate_task_to_member" ||
            lower === "delegate_task_to_members" ||
            lower === "transfer_task_to_member" ||
            lower === "transfer_task_to_members"
          );
        }

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
                // ── Team lifecycle ─────────────────────────────
                case "TeamRunStarted": {
                  writer.write({
                    type: "data-team-run-started" as `data-${string}`,
                    data: {
                      team_name: parsed.team_name || parsed.agent_name || "FinX Team",
                      model: parsed.model || "",
                      session_id: parsed.session_id || null,
                    },
                  });
                  break;
                }

                // ── Team-level tool call (e.g. delegate_task_to_member) ─
                case "TeamToolCallStarted": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const toolName = (tool?.tool_name as string) || "";
                  if (isInternalToolCall(toolName)) {
                    // Extract member_id from delegate args for pending delegation
                    const toolArgs = (tool?.tool_args as Record<string, unknown>) || {};
                    pendingMemberDelegation = (toolArgs.member_id as string) || "";
                  }
                  break;
                }

                case "TeamToolCallCompleted": {
                  // Ignore — just acknowledge internal delegation completion
                  break;
                }

                case "TeamModelRequestStarted":
                case "TeamModelRequestCompleted":
                case "ModelRequestStarted":
                case "ModelRequestCompleted": {
                  // Ignore model request lifecycle events — no UI needed
                  break;
                }

                case "TeamRunCompleted": {
                  // Emit final content only if no content was streamed yet.
                  // The Agno framework may send the full coordinator summary
                  // only in TeamRunCompleted when members did all the work.
                  if (!textStarted && parsed.content) {
                    if (emitFinalContent(writer, textPartId, parsed.content as string)) {
                      textStarted = true;
                    }
                  }

                  if (parsed.session_id) {
                    writer.write({
                      type: "data-session" as `data-${string}`,
                      data: { session_id: parsed.session_id },
                    });
                  }

                  // Emit run metrics (tokens, cost, timing)
                  const metrics = (parsed.metrics as Record<string, unknown>) || {};
                  writer.write({
                    type: "data-run-metrics" as `data-${string}`,
                    data: {
                      input_tokens: metrics.input_tokens || parsed.input_tokens || 0,
                      output_tokens: metrics.output_tokens || parsed.output_tokens || 0,
                      total_tokens: metrics.total_tokens || parsed.total_tokens || 0,
                      time_to_first_token: metrics.time_to_first_token || parsed.time_to_first_token || null,
                      reasoning_tokens: metrics.reasoning_tokens || parsed.reasoning_tokens || 0,
                    },
                  });
                  break;
                }

                // ── Member agent delegation ───────────────────
                case "MemberRunStarted": {
                  memberCounter++;
                  const memberName =
                    (parsed.member_name as string) ||
                    (parsed.agent_name as string) ||
                    `Agent ${memberCounter}`;
                  activeMemberId = `member-${memberCounter}`;
                  writer.write({
                    type: "data-member-started" as `data-${string}`,
                    data: {
                      id: activeMemberId,
                      name: memberName,
                      model: parsed.model || "",
                    },
                  });
                  break;
                }

                case "MemberRunContent": {
                  const rawMemberContent = (parsed.content as string) || "";
                  const cleanMemberContent = rawMemberContent ? stripFrameworkNoise(rawMemberContent) : "";
                  if (cleanMemberContent && !isFrameworkNoise(cleanMemberContent)) {
                    writer.write({
                      type: "data-member-content" as `data-${string}`,
                      data: {
                        id: `member-${memberCounter}`,
                        name: (parsed.member_name as string) || (parsed.agent_name as string) || "",
                        delta: cleanMemberContent,
                      },
                    });
                  }
                  break;
                }

                case "MemberRunCompleted": {
                  const memberMetrics = (parsed.metrics as Record<string, unknown>) || {};
                  const rawMemberFinal = (parsed.content as string) || "";
                  const cleanMemberFinal = rawMemberFinal ? stripFrameworkNoise(rawMemberFinal) : "";
                  writer.write({
                    type: "data-member-completed" as `data-${string}`,
                    data: {
                      id: `member-${memberCounter}`,
                      name: (parsed.member_name as string) || (parsed.agent_name as string) || "",
                      content: cleanMemberFinal,
                      input_tokens: memberMetrics.input_tokens || parsed.input_tokens || 0,
                      output_tokens: memberMetrics.output_tokens || parsed.output_tokens || 0,
                      total_tokens: memberMetrics.total_tokens || parsed.total_tokens || 0,
                    },
                  });
                  activeMemberId = "";
                  break;
                }

                case "MemberRunError": {
                  writer.write({
                    type: "data-member-error" as `data-${string}`,
                    data: {
                      id: `member-${memberCounter}`,
                      name: (parsed.member_name as string) || (parsed.agent_name as string) || "",
                      error: (parsed.content as string) || (parsed.error as string) || "Member agent error",
                    },
                  });
                  activeMemberId = "";
                  break;
                }

                // ── Run lifecycle (single agent / coordinator) ─
                case "RunStarted": {
                  // If there is a parent_run_id, this is a member agent run
                  const agentName = (parsed.agent_name as string) || "";
                  const parentRunId = parsed.parent_run_id as string | undefined;

                  if (parentRunId || pendingMemberDelegation) {
                    // Guard: if MemberRunStarted already created this member, skip
                    if (activeMemberId) {
                      break;
                    }
                    // This is a member agent starting
                    memberCounter++;
                    const memberName = agentName || pendingMemberDelegation || `Agent ${memberCounter}`;
                    activeMemberId = `member-${memberCounter}`;
                    pendingMemberDelegation = "";
                    writer.write({
                      type: "data-member-started" as `data-${string}`,
                      data: {
                        id: activeMemberId,
                        name: memberName,
                        model: (parsed.model as string) || "",
                      },
                    });
                  } else {
                    writer.write({
                      type: "data-run-started" as `data-${string}`,
                      data: {
                        model: parsed.model || "",
                        model_provider: parsed.model_provider || "",
                        session_id: parsed.session_id || null,
                        agent_name: agentName,
                      },
                    });
                  }
                  break;
                }

                // ── Reasoning / Thinking ──────────────────────
                case "ReasoningStarted": {
                  reasoningPartId = crypto.randomUUID();
                  reasoningStarted = true;
                  writer.write({
                    type: "data-reasoning-started" as `data-${string}`,
                    data: { id: reasoningPartId, memberId: activeMemberId || undefined },
                  });
                  break;
                }

                case "ReasoningContentDelta": {
                  const delta = (parsed.reasoning_content as string) || "";
                  if (delta) {
                    writer.write({
                      type: "data-reasoning-delta" as `data-${string}`,
                      data: { id: reasoningPartId, delta, memberId: activeMemberId || undefined },
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
                      data: { id: reasoningPartId, delta: stepContent, memberId: activeMemberId || undefined },
                    });
                  }
                  break;
                }

                case "ReasoningCompleted": {
                  if (reasoningStarted) {
                    writer.write({
                      type: "data-reasoning-completed" as `data-${string}`,
                      data: { id: reasoningPartId, memberId: activeMemberId || undefined },
                    });
                    reasoningStarted = false;
                  }
                  break;
                }

                // ── Tool calls ────────────────────────────────
                case "ToolCallStarted": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const toolName = (tool?.tool_name as string) || "unknown";
                  // Skip internal Agno delegation tool calls
                  if (isInternalToolCall(toolName)) break;
                  toolCallCounter++;
                  const tcStartId = (tool?.tool_call_id as string) || `tc-${toolCallCounter}`;
                  writer.write({
                    type: "data-tool-call-started" as `data-${string}`,
                    data: {
                      id: tcStartId,
                      name: toolName,
                      args: tool?.tool_args || {},
                      memberId: activeMemberId || undefined,
                    },
                  });
                  break;
                }

                case "ToolCallCompleted": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const toolName = (tool?.tool_name as string) || "unknown";
                  // Skip internal Agno delegation tool calls
                  if (isInternalToolCall(toolName)) break;
                  // Use tool.result only — parsed.content is Agno execution log noise
                  const resultStr = (tool?.result as string) || "";
                  const tcCompleteId = (tool?.tool_call_id as string) || `tc-${toolCallCounter}`;
                  writer.write({
                    type: "data-tool-call-completed" as `data-${string}`,
                    data: {
                      id: tcCompleteId,
                      name: toolName,
                      result: resultStr,
                      error: tool?.tool_call_error || false,
                      memberId: activeMemberId || undefined,
                    },
                  });
                  break;
                }

                case "ToolCallError": {
                  const tool = parsed.tool as Record<string, unknown> | undefined;
                  const toolName = (tool?.tool_name as string) || "unknown";
                  // Skip internal Agno delegation tool calls
                  if (isInternalToolCall(toolName)) break;
                  const tcErrorId = (tool?.tool_call_id as string) || `tc-${toolCallCounter}`;
                  writer.write({
                    type: "data-tool-call-completed" as `data-${string}`,
                    data: {
                      id: tcErrorId,
                      name: toolName,
                      result: (parsed.error as string) || "Tool call failed",
                      error: true,
                      memberId: activeMemberId || undefined,
                    },
                  });
                  break;
                }

                // ── Content tokens (coordinator or fallback) ──
                case "TeamRunContent":
                case "RunContent": {
                  const rawContent = (parsed.content as string) || "";
                  // Strip Agno framework noise from content
                  const cleanContent = rawContent ? stripFrameworkNoise(rawContent) : "";

                  // If inside a member run, route content ONLY to the member
                  // — do NOT also emit as main text-delta (avoids duplicate)
                  if (activeMemberId && currentEvent === "RunContent") {
                    if (cleanContent && !isFrameworkNoise(cleanContent)) {
                      writer.write({
                        type: "data-member-content" as `data-${string}`,
                        data: {
                          id: activeMemberId,
                          name: (parsed.agent_name as string) || "",
                          delta: cleanContent,
                        },
                      });
                    }
                  } else {
                    // Coordinator / team-level content → main chat text
                    if (cleanContent && !isFrameworkNoise(cleanContent)) {
                      if (!textStarted) {
                        writer.write({ type: "text-start", id: textPartId });
                        textStarted = true;
                      }
                      writer.write({
                        type: "text-delta",
                        id: textPartId,
                        delta: cleanContent,
                      });
                    }
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

                // ── Run completed (single agent) ─────────────
                case "RunCompleted": {
                  const parentRunId = parsed.parent_run_id as string | undefined;

                  // If this is a member agent completing (has parent_run_id or active member)
                  if (parentRunId || activeMemberId) {
                    const memberMetrics = (parsed.metrics as Record<string, unknown>) || {};
                    const rawMemberFinal = (parsed.content as string) || "";
                    const cleanMemberFinal = rawMemberFinal ? stripFrameworkNoise(rawMemberFinal) : "";
                    writer.write({
                      type: "data-member-completed" as `data-${string}`,
                      data: {
                        id: activeMemberId || `member-${memberCounter}`,
                        name: (parsed.agent_name as string) || "",
                        content: cleanMemberFinal,
                        input_tokens: memberMetrics.input_tokens || parsed.input_tokens || 0,
                        output_tokens: memberMetrics.output_tokens || parsed.output_tokens || 0,
                        total_tokens: memberMetrics.total_tokens || parsed.total_tokens || 0,
                      },
                    });
                    activeMemberId = "";
                    // Do NOT emit member content as main text — it lives in the member card only
                  } else {
                    // Coordinator / single-agent completed — emit as main text
                    if (!textStarted && parsed.content) {
                      if (emitFinalContent(writer, textPartId, parsed.content as string)) {
                        textStarted = true;
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

                // ── Errors ────────────────────────────────────
                case "RunError": {
                  // If inside a member run, emit ONLY as member error
                  if (activeMemberId) {
                    writer.write({
                      type: "data-member-error" as `data-${string}`,
                      data: {
                        id: activeMemberId,
                        name: (parsed.agent_name as string) || "",
                        error: (parsed.content as string) || (parsed.error as string) || "Agent error",
                      },
                    });
                    activeMemberId = "";
                  } else {
                    // Coordinator-level error → show in main chat
                    writer.write({
                      type: "error",
                      errorText: (parsed.content as string) || "An error occurred",
                    });
                  }
                  break;
                }
                case "TeamRunError": {
                  writer.write({
                    type: "error",
                    errorText: (parsed.content as string) || "An error occurred",
                  });
                  break;
                }

                // ── Fallback: content from unknown event ──────
                default: {
                  // Skip fallback content when inside a member run to avoid duplication
                  if (activeMemberId) break;

                  if (parsed.content && typeof parsed.content === "string") {
                    const cleanFallback = stripFrameworkNoise(parsed.content);
                    if (cleanFallback && !isFrameworkNoise(cleanFallback)) {
                      if (!textStarted) {
                        writer.write({ type: "text-start", id: textPartId });
                        textStarted = true;
                      }
                      writer.write({
                        type: "text-delta",
                        id: textPartId,
                        delta: cleanFallback,
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
