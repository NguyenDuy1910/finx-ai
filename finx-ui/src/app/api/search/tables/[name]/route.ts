import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { TableDetailResponse } from "@/types";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  try {
    const { name } = await params;
    const data = await fetchJSON<TableDetailResponse>(
      `/api/v1/search/tables/${encodeURIComponent(name)}`
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
