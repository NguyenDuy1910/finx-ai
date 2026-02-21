import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { TableResponse } from "@/types";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const params = new URLSearchParams();

    const database = searchParams.get("database");
    const offset = searchParams.get("offset");
    const limit = searchParams.get("limit");

    if (database) params.set("database", database);
    if (offset) params.set("offset", offset);
    if (limit) params.set("limit", limit);

    const query = params.toString();
    const path = `/api/v1/graph/tables${query ? `?${query}` : ""}`;

    const data = await fetchJSON<TableResponse[]>(path);
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
