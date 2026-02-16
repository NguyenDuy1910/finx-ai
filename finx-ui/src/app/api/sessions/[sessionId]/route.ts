import { NextRequest, NextResponse } from "next/server";
import { fetchJSON } from "@/lib/api";

/**
 * GET /api/sessions/[sessionId]
 *
 * Proxies to AgentOS  GET /sessions/{session_id}  to retrieve a session's
 * messages so the UI can restore a chat thread when the user clicks on it.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    const data = await fetchJSON<unknown>(
      `/sessions/${sessionId}`,
      { method: "GET" }
    );
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to fetch session";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
