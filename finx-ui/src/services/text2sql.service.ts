import type { Text2SQLResponse } from "@/types/search.types";

export async function generateSQL(
  query: string,
  database: string
): Promise<Text2SQLResponse> {
  const res = await fetch("/api/text2sql", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, database }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || "Failed to generate SQL");
  }
  return res.json();
}
