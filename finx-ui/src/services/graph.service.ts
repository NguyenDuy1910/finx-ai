import type { StatsResponse, IndexSchemaResponse, FeedbackResponse } from "@/types/admin.types";

export async function fetchGraphStats(): Promise<StatsResponse> {
  const res = await fetch("/api/graph/stats");
  if (!res.ok) throw new Error("Failed to load stats");
  return res.json();
}

export async function indexSchema(
  schemaPath: string,
  database: string,
  skipExisting: boolean
): Promise<IndexSchemaResponse> {
  const res = await fetch("/api/graph/index", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      schema_path: schemaPath,
      database,
      skip_existing: skipExisting,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || "Indexing failed");
  }
  return res.json();
}

export async function submitFeedback(payload: {
  natural_language: string;
  generated_sql: string;
  feedback: string;
  rating: number | null;
  corrected_sql: string;
}): Promise<FeedbackResponse> {
  const res = await fetch("/api/graph/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || "Failed to submit feedback");
  }
  return res.json();
}
