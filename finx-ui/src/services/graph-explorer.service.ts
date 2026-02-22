import type {
  GraphNode,
  GraphNodeListResponse,
  GraphEdge,
  GraphEdgeListResponse,
  CreateNodeRequest,
  UpdateNodeRequest,
  CreateEdgeRequest,
  UpdateEdgeRequest,
  ExploreNodeResponse,
  LineageResponse,
  GraphOverviewResponse,
  GraphSearchResponse,
} from "@/types/graph-explorer.types";

const BASE = "/api/graph/explorer";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== ""
  );
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

export async function fetchNodes(
  label: string,
  params?: { offset?: number; limit?: number; search?: string }
): Promise<GraphNodeListResponse> {
  const query = buildQuery({
    offset: params?.offset,
    limit: params?.limit,
    search: params?.search,
  });
  return request<GraphNodeListResponse>(`/nodes/${label}${query}`);
}

export async function fetchNode(label: string, uuid: string): Promise<GraphNode> {
  return request<GraphNode>(`/nodes/${label}/${uuid}`);
}

export async function createNode(
  label: string,
  body: Omit<CreateNodeRequest, "label">
): Promise<GraphNode> {
  return request<GraphNode>(`/nodes/${label}`, {
    method: "POST",
    body: JSON.stringify({ label, ...body }),
  });
}

export async function updateNode(
  label: string,
  uuid: string,
  body: UpdateNodeRequest
): Promise<GraphNode> {
  return request<GraphNode>(`/nodes/${label}/${uuid}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteNode(label: string, uuid: string): Promise<void> {
  return request<void>(`/nodes/${label}/${uuid}`, { method: "DELETE" });
}

export async function fetchEdges(params?: {
  source_uuid?: string;
  target_uuid?: string;
  edge_type?: string;
  offset?: number;
  limit?: number;
}): Promise<GraphEdgeListResponse> {
  const query = buildQuery({
    source_uuid: params?.source_uuid,
    target_uuid: params?.target_uuid,
    edge_type: params?.edge_type,
    offset: params?.offset,
    limit: params?.limit,
  });
  return request<GraphEdgeListResponse>(`/edges${query}`);
}

export async function fetchEdge(uuid: string): Promise<GraphEdge> {
  return request<GraphEdge>(`/edges/${uuid}`);
}

export async function createEdge(body: CreateEdgeRequest): Promise<GraphEdge> {
  return request<GraphEdge>("/edges", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateEdge(uuid: string, body: UpdateEdgeRequest): Promise<GraphEdge> {
  return request<GraphEdge>(`/edges/${uuid}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteEdge(uuid: string): Promise<void> {
  return request<void>(`/edges/${uuid}`, { method: "DELETE" });
}

export async function fetchExploreNode(uuid: string): Promise<ExploreNodeResponse> {
  return request<ExploreNodeResponse>(`/explore/${uuid}`);
}

export async function expandNode(uuid: string): Promise<ExploreNodeResponse> {
  return request<ExploreNodeResponse>(`/explore/${uuid}/expand`);
}

export async function fetchLineage(uuid: string): Promise<LineageResponse> {
  return request<LineageResponse>(`/lineage/${uuid}`);
}

export async function fetchGraphOverview(): Promise<GraphOverviewResponse> {
  return request<GraphOverviewResponse>("/overview");
}

export async function searchGraph(
  q: string,
  label?: string,
  limit?: number
): Promise<GraphSearchResponse> {
  const query = buildQuery({ q, label, limit });
  return request<GraphSearchResponse>(`/search${query}`);
}

export async function semanticSearchGraph(
  q: string,
  label?: string,
  limit?: number
): Promise<GraphSearchResponse> {
  const query = buildQuery({ q, label, limit });
  return request<GraphSearchResponse>(`/search/semantic${query}`);
}
