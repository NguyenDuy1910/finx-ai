import { NextRequest, NextResponse } from "next/server";
import { fetchJSON, BackendError } from "@/lib/api";
import { FeedbackResponse } from "@/types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (!body.natural_language || !body.generated_sql || !body.feedback) {
      return NextResponse.json(
        { error: "natural_language, generated_sql, and feedback are required" },
        { status: 400 }
      );
    }

    const data = await fetchJSON<FeedbackResponse>("/api/v1/graph/feedback", {
      method: "POST",
      body: JSON.stringify({
        natural_language: body.natural_language,
        generated_sql: body.generated_sql,
        feedback: body.feedback,
        rating: body.rating ?? null,
        corrected_sql: body.corrected_sql || "",
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
