import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import type { SyncResponse } from "@/types/indexing.types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const data = await fetchJSON<SyncResponse>("/api/v1/indexing/sync", {
      method: "POST",
      body: JSON.stringify(body),
    });
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
