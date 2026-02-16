import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { IndexSchemaResponse } from "@/types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const data = await fetchJSON<IndexSchemaResponse>("/api/v1/graph/index", {
      method: "POST",
      body: JSON.stringify({
        schema_path: body.schema_path,
        database: body.database || null,
        skip_existing: body.skip_existing ?? false,
      }),
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
