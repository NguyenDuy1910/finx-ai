import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8080";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/indexing/progress`, {
      signal: AbortSignal.timeout(10_000),
    });
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(
        { error: data.detail ?? "Failed to get progress" },
        { status: res.status }
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to connect to backend";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
