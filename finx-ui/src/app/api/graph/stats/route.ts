import { NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { StatsResponse } from "@/types";

export async function GET() {
  try {
    const data = await fetchJSON<StatsResponse>("/api/v1/graph/stats");
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
