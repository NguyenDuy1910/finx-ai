import { NextRequest, NextResponse } from "next/server";
import { fetchJSON } from "@/lib/api";

/**
 * GET /api/sessions?agent_id=knowledge-agent
 *
 * Proxies to AgentOS  GET /sessions  to list all stored sessions.
 * The UI uses this to hydrate the sidebar on first load.
 */
export async function GET(req: NextRequest) {
  try {
    const agentId = req.nextUrl.searchParams.get("agent_id") || "knowledge-agent";
    const data = await fetchJSON<unknown>(
      `/agents/${agentId}/sessions`,
      { method: "GET" }
    );
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to fetch sessions";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
