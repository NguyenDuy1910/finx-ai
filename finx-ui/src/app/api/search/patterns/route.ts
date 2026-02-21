import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const query = searchParams.get("query");

    if (!query) {
      return NextResponse.json(
        { error: "query is required" },
        { status: 400 }
      );
    }

    const data = await fetchJSON<unknown>(
      `/api/v1/search/patterns?query=${encodeURIComponent(query)}`
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
