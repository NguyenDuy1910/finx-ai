from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from src.web.v1.deps import AppState, get_app_state
from src.web.v1.schemas_graph_explorer import (
    GraphNodeResponse,
    GraphNodeListResponse,
    CreateNodeRequest,
    UpdateNodeRequest,
    GraphEdgeResponse,
    GraphEdgeListResponse,
    CreateEdgeRequest,
    UpdateEdgeRequest,
    ExploreNodeResponse,
    LineageResponse,
    GraphOverviewResponse,
    GraphOverviewDomain,
    GraphSearchResponse,
)
from src.web.v1.services.graph_explorer_service import GraphExplorerService

router = APIRouter(prefix="/graph/explorer", tags=["graph-explorer"])


def _get_service(state: AppState = Depends(get_app_state)) -> GraphExplorerService:
    return GraphExplorerService(client=state.client)


@router.get("/nodes/{label}", response_model=GraphNodeListResponse)
async def list_nodes(
    label: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        result = await svc.list_nodes(label, offset, limit, search)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GraphNodeListResponse(**result)


@router.get("/nodes/{label}/{uuid}", response_model=GraphNodeResponse)
async def get_node(
    label: str,
    uuid: str,
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        result = await svc.get_node(label, uuid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return GraphNodeResponse(**result)


@router.post("/nodes/{label}", response_model=GraphNodeResponse, status_code=201)
async def create_node(
    label: str,
    body: CreateNodeRequest,
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        result = await svc.create_node(label, body.name, body.description, body.attributes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GraphNodeResponse(**result)


@router.put("/nodes/{label}/{uuid}", response_model=GraphNodeResponse)
async def update_node(
    label: str,
    uuid: str,
    body: UpdateNodeRequest,
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        result = await svc.update_node(label, uuid, body.name, body.description, body.attributes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return GraphNodeResponse(**result)


@router.delete("/nodes/{label}/{uuid}", status_code=204)
async def delete_node(
    label: str,
    uuid: str,
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        deleted = await svc.delete_node(label, uuid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")


@router.get("/edges", response_model=GraphEdgeListResponse)
async def list_edges(
    source_uuid: Optional[str] = Query(None),
    target_uuid: Optional[str] = Query(None),
    edge_type: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    svc: GraphExplorerService = Depends(_get_service),
):
    result = await svc.list_edges(source_uuid, target_uuid, edge_type, offset, limit)
    return GraphEdgeListResponse(**result)


@router.get("/edges/{uuid}", response_model=GraphEdgeResponse)
async def get_edge(
    uuid: str,
    svc: GraphExplorerService = Depends(_get_service),
):
    result = await svc.get_edge(uuid)
    if result is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    return GraphEdgeResponse(**result)


@router.post("/edges", response_model=GraphEdgeResponse, status_code=201)
async def create_edge(
    body: CreateEdgeRequest,
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        result = await svc.create_edge(
            body.source_uuid, body.target_uuid, body.edge_type, body.fact, body.attributes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GraphEdgeResponse(**result)


@router.put("/edges/{uuid}", response_model=GraphEdgeResponse)
async def update_edge(
    uuid: str,
    body: UpdateEdgeRequest,
    svc: GraphExplorerService = Depends(_get_service),
):
    result = await svc.update_edge(uuid, body.fact, body.attributes)
    if result is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    return GraphEdgeResponse(**result)


@router.delete("/edges/{uuid}", status_code=204)
async def delete_edge(
    uuid: str,
    svc: GraphExplorerService = Depends(_get_service),
):
    deleted = await svc.delete_edge(uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")


@router.get("/explore/{uuid}", response_model=ExploreNodeResponse)
async def explore_node(
    uuid: str,
    svc: GraphExplorerService = Depends(_get_service),
):
    result = await svc.explore_node(uuid)
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return ExploreNodeResponse(**result)


@router.get("/explore/{uuid}/expand", response_model=ExploreNodeResponse)
async def expand_node(
    uuid: str,
    svc: GraphExplorerService = Depends(_get_service),
):
    result = await svc.expand_node(uuid)
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return ExploreNodeResponse(**result)


@router.get("/lineage/{uuid}", response_model=LineageResponse)
async def get_lineage(
    uuid: str,
    svc: GraphExplorerService = Depends(_get_service),
):
    result = await svc.get_lineage(uuid)
    return LineageResponse(**result)


@router.get("/overview", response_model=GraphOverviewResponse)
async def get_overview(
    svc: GraphExplorerService = Depends(_get_service),
):
    result = await svc.get_overview()
    domains = [GraphOverviewDomain(**d) for d in result.get("domains", [])]
    return GraphOverviewResponse(domains=domains, stats=result.get("stats", {}))


@router.get("/search", response_model=GraphSearchResponse)
async def search_graph(
    q: str = Query(..., min_length=1),
    label: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        result = await svc.search_nodes(q, label, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GraphSearchResponse(**result)


@router.get("/search/semantic", response_model=GraphSearchResponse)
async def search_graph_semantic(
    q: str = Query(..., min_length=1),
    label: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    svc: GraphExplorerService = Depends(_get_service),
):
    try:
        result = await svc.search_nodes_by_embedding(q, label, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GraphSearchResponse(**result)
