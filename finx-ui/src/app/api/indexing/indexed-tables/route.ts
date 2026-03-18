import { NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";

/**
 * GET /api/indexing/indexed-tables
 * Returns the list of table names already indexed in the knowledge graph.
 */
export async function GET() {
  try {
    const data = await fetchJSON<{ tables: string[]; count: number }>(
      "/api/v1/indexing/indexed-tables"
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
