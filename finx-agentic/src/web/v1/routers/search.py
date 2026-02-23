from fastapi import APIRouter, Depends, Query

from src.web.v1.deps import AppState, get_app_state
from src.web.v1.schemas import (
    SearchRequest,
    SearchResponse,
    TableDetailResponse,
    RelatedTablesResponse,
    JoinPathResponse,
)
from src.web.v1.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


def _get_service(state: AppState = Depends(get_app_state)) -> SearchService:
    return SearchService(memory=state.memory)


@router.post("/schemas")
async def search_schemas(
    body: SearchRequest,
    svc: SearchService = Depends(_get_service),
) -> SearchResponse:
    result = await svc.search_schema(
        query=body.query,
        domain=body.domain,
        entities=body.entities,
        top_k=body.top_k,
    )
    return SearchResponse(
        tables=result.get("tables", []),
        columns=result.get("columns", []),
        entities=result.get("entities", []),
        patterns=result.get("patterns", []),
        context=result.get("context", []),
    )


@router.get("/tables/{table_name}")
async def get_table(
    table_name: str,
    database: str = Query(default=None),
    svc: SearchService = Depends(_get_service),
) -> TableDetailResponse:
    result = await svc.get_table_details(table_name, database)
    return TableDetailResponse(
        table=result.get("table"),
        columns=result.get("columns", []),
        edges=result.get("edges", []),
    )


@router.get("/tables/{table_name}/related")
async def get_related(
    table_name: str,
    database: str = Query(default=None),
    svc: SearchService = Depends(_get_service),
) -> RelatedTablesResponse:
    result = await svc.find_related_tables(table_name, database)
    return RelatedTablesResponse(
        table=table_name,
        relations=result.get("relations", []),
    )


@router.get("/join-path")
async def get_join_path(
    source: str = Query(...),
    target: str = Query(...),
    database: str = Query(default=None),
    svc: SearchService = Depends(_get_service),
) -> JoinPathResponse:
    result = await svc.find_join_path(source, target, database)
    return JoinPathResponse(
        source=result.get("source", source),
        target=result.get("target", target),
        direct_joins=result.get("direct_joins", []),
        shared_intermediates=result.get("shared_intermediates", []),
    )


@router.get("/terms/{term}")
async def resolve_term(
    term: str,
    svc: SearchService = Depends(_get_service),
):
    return await svc.resolve_term(term)


@router.get("/domains")
async def list_domains(svc: SearchService = Depends(_get_service)):
    return await svc.discover_domains()


@router.get("/patterns")
async def get_patterns(
    query: str = Query(...),
    svc: SearchService = Depends(_get_service),
):
    return await svc.get_query_patterns(query)


@router.get("/similar-queries")
async def similar_queries(
    query: str = Query(...),
    top_k: int = Query(default=5),
    svc: SearchService = Depends(_get_service),
):
    return await svc.get_similar_queries(query, top_k=top_k)
