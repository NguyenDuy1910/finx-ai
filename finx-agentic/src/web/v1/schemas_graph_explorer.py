from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GraphNodeResponse(BaseModel):
    uuid: str
    name: str
    label: str
    summary: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class GraphNodeListResponse(BaseModel):
    nodes: List[GraphNodeResponse]
    total: int
    offset: int
    limit: int


class CreateNodeRequest(BaseModel):
    label: str
    name: str
    description: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)


class UpdateNodeRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class GraphEdgeResponse(BaseModel):
    uuid: str
    edge_type: str
    source_node: GraphNodeResponse
    target_node: GraphNodeResponse
    fact: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)


class GraphEdgeListResponse(BaseModel):
    edges: List[GraphEdgeResponse]
    total: int
    offset: int
    limit: int


class CreateEdgeRequest(BaseModel):
    source_uuid: str
    target_uuid: str
    edge_type: str
    fact: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)


class UpdateEdgeRequest(BaseModel):
    fact: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class ExploreNodeResponse(BaseModel):
    center: GraphNodeResponse
    neighbors: List[GraphNodeResponse]
    edges: List[GraphEdgeResponse]


class LineageResponse(BaseModel):
    nodes: List[GraphNodeResponse]
    edges: List[GraphEdgeResponse]
    paths: List[List[str]] = Field(default_factory=list)


class GraphOverviewDomain(BaseModel):
    uuid: str
    name: str
    table_count: int = 0
    entity_count: int = 0


class GraphOverviewResponse(BaseModel):
    domains: List[GraphOverviewDomain] = Field(default_factory=list)
    stats: Dict[str, int] = Field(default_factory=dict)


class GraphSearchResponse(BaseModel):
    nodes: List[GraphNodeResponse]
    total: int
