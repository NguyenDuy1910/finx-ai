import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { Text2SQLResponse } from "@/types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (!body.query || typeof body.query !== "string") {
      return NextResponse.json(
        { error: "query is required" },
        { status: 400 }
      );
    }

    const data = await fetchJSON<Text2SQLResponse>("/api/v1/sql/generate", {
      method: "POST",
      body: JSON.stringify({
        query: body.query,
        database: body.database || null,
        session_id: body.session_id || null,
      }),
    });

    return NextResponse.json(data);
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
