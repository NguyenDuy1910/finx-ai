import type { KnowledgeSummary } from "@/types/knowledge.types";

export async function fetchKnowledgeSummary(): Promise<KnowledgeSummary> {
  const res = await fetch("/api/knowledge/summary");
  if (!res.ok) throw new Error("Failed to load knowledge summary");
  return res.json();
}
