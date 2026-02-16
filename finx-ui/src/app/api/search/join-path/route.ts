import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { JoinPathResponse } from "@/types";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const source = searchParams.get("source");
    const target = searchParams.get("target");

    if (!source || !target) {
      return NextResponse.json(
        { error: "source and target are required" },
        { status: 400 }
      );
    }

    const params = new URLSearchParams({ source, target });
    const database = searchParams.get("database");
    if (database) params.set("database", database);

    const data = await fetchJSON<JoinPathResponse>(
      `/api/v1/search/join-path?${params}`
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
