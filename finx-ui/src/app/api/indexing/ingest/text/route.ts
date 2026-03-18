import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";

const INGEST_TIMEOUT = 300_000;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const response = await fetchFromBackend("/api/v1/indexing/ingest/text", {
      method: "POST",
      body: JSON.stringify(body),
      timeout: INGEST_TIMEOUT,
    });

    if (!response.ok) {
      let detail = `Backend returned ${response.status}`;
      try {
        const errBody = await response.json();
        detail = errBody.detail || errBody.error || detail;
      } catch {
        detail = await response.text().catch(() => detail);
      }
      return NextResponse.json({ error: detail }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ error: error.detail }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Failed to ingest text";
    const isAbort = error instanceof Error && error.name === "AbortError";
    return NextResponse.json(
      { error: isAbort ? "Request timed out — the ingestion is still running on the backend" : message },
      { status: isAbort ? 504 : 502 }
    );
  }
}
