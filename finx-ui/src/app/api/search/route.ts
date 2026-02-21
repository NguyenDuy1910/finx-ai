import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";

interface SearchResponseData {
  tables: Record<string, unknown>[];
  columns: Record<string, unknown>[];
  entities: Record<string, unknown>[];
  patterns: Record<string, unknown>[];
  context: Record<string, unknown>[];
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (!body.query || typeof body.query !== "string") {
      return NextResponse.json(
        { error: "query is required" },
        { status: 400 }
      );
    }

    const data = await fetchJSON<SearchResponseData>(
      "/api/v1/search/schemas",
      {
        method: "POST",
        body: JSON.stringify({
          query: body.query,
          database: body.database || null,
          domain: body.domain || null,
          entities: body.entities || null,
          top_k: body.top_k || 5,
        }),
      }
    );

    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        { error: error.detail },
        { status: error.status }
      );
    }
    return NextResponse.json(
      { error: "Failed to connect to backend" },
      { status: 502 }
    );
  }
}
