import { NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { HealthResponse } from "@/types";

export async function GET() {
  try {
    const data = await fetchJSON<HealthResponse>("/api/v1/health", {
      timeout: 5000,
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        { status: "error", graph_connected: false, version: "unknown" },
        { status: error.status }
      );
    }
    return NextResponse.json(
      { status: "unreachable", graph_connected: false, version: "unknown" },
      { status: 502 }
    );
  }
}
