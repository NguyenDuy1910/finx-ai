import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ term: string }> }
) {
  try {
    const { term } = await params;
    const data = await fetchJSON<unknown>(
      `/api/v1/search/terms/${encodeURIComponent(term)}`
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
