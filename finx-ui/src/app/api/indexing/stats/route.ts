import { NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import type { GraphIndexingStats } from "@/types/indexing.types";

export async function GET() {
  try {
    const data = await fetchJSON<GraphIndexingStats>("/api/v1/indexing/stats");
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
