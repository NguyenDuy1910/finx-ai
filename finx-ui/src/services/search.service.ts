import type {
  SchemaSearchResponse,
  TableDetailResponse,
  RelatedTablesResponse,
  JoinPathResponse,
} from "@/types/search.types";

export async function searchSchema(
  query: string,
  database: string,
  topK = 10
): Promise<SchemaSearchResponse> {
  const res = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, database, top_k: topK }),
  });
  if (!res.ok) throw new Error("Search failed");
  return res.json();
}

export async function fetchTableDetail(
  tableName: string
): Promise<TableDetailResponse> {
  const res = await fetch(
    `/api/search/tables/${encodeURIComponent(tableName)}`
  );
  if (!res.ok) throw new Error("Failed to load table detail");
  return res.json();
}

export async function fetchRelatedTables(
  tableName: string
): Promise<RelatedTablesResponse> {
  const res = await fetch(
    `/api/search/tables/${encodeURIComponent(tableName)}/related`
  );
  if (!res.ok) throw new Error("Failed to load related tables");
  return res.json();
}

export async function fetchJoinPath(
  source: string,
  target: string
): Promise<JoinPathResponse> {
  const params = new URLSearchParams({ source, target });
  const res = await fetch(`/api/search/join-path?${params}`);
  if (!res.ok) throw new Error("Join path lookup failed");
  return res.json();
}

export async function fetchTerms(term: string): Promise<unknown> {
  const res = await fetch(
    `/api/search/terms/${encodeURIComponent(term)}`
  );
  if (!res.ok) throw new Error("Term lookup failed");
  return res.json();
}

export async function fetchDomains(): Promise<unknown> {
  const res = await fetch("/api/search/domains");
  if (!res.ok) throw new Error("Failed to load domains");
  return res.json();
}

export async function fetchPatterns(query: string): Promise<unknown> {
  const res = await fetch(
    `/api/search/patterns?query=${encodeURIComponent(query)}`
  );
  if (!res.ok) throw new Error("Patterns lookup failed");
  return res.json();
}

export async function fetchSimilarQueries(
  query: string,
  topK = 5
): Promise<unknown> {
  const res = await fetch(
    `/api/search/similar-queries?query=${encodeURIComponent(query)}&top_k=${topK}`
  );
  if (!res.ok) throw new Error("Similar queries lookup failed");
  return res.json();
}
