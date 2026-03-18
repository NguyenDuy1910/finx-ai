import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8080";

/**
 * POST /api/table-indexing/pipeline
 *
 * The "full pipeline" endpoint. The backend doesn't have a single /pipeline
 * endpoint — instead we proxy to /api/v1/indexing/run which handles
 * enrichment + indexing in one shot if given full TableSchema objects.
 *
 * Frontend sends: { tables: TableSchema[], skip_existing?, ... }
 * Backend expects: { tables: List[TableSchema], skip_existing: bool }
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const backendRes = await fetch(`${BACKEND_URL}/api/v1/indexing/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tables: body.tables ?? [],
        skip_existing: body.skip_existing ?? body.only_new ?? true,
      }),
      signal: AbortSignal.timeout(600_000), // 10 min
    });

    const data = await backendRes.json();

    if (!backendRes.ok) {
      return NextResponse.json(
        { error: data.detail ?? data.error ?? "Pipeline failed" },
        { status: backendRes.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to connect to backend";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
