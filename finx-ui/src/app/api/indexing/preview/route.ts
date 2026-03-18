import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";
import type { PreviewResponse } from "@/types/indexing.types";

/**
 * Increased timeout for preview — LLM enrichment of large tables can take >60s.
 * Stream the raw request body to avoid double-parse/serialize overhead.
 */
const PREVIEW_TIMEOUT = 120_000; // 120s

export async function POST(req: NextRequest) {
  try {
    // Forward the raw body stream to avoid double JSON parse/stringify
    const rawBody = await req.text();
    const response = await fetchFromBackend("/api/v1/indexing/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: rawBody,
      timeout: PREVIEW_TIMEOUT,
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

    const data: PreviewResponse = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        { error: error.detail },
        { status: error.status }
      );
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      return NextResponse.json(
        { error: "Preview request timed out — table metadata may be too large" },
        { status: 504 }
      );
    }
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to connect to backend" },
      { status: 502 }
    );
  }
}
