from fastapi import APIRouter, Depends

from src.web.v1.deps import AppState, get_app_state
from src.web.v1.schemas import (
    IndexSchemaRequest,
    IndexSchemaResponse,
    GraphStatsResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from src.web.v1.services.indexing_service import IndexingService

router = APIRouter(prefix="/graph", tags=["graph"])


def _get_service(state: AppState = Depends(get_app_state)) -> IndexingService:
    return IndexingService(
        client=state.client,
        memory=state.memory,
    )


@router.post("/index")
async def index_schemas(
    body: IndexSchemaRequest,
    svc: IndexingService = Depends(_get_service),
) -> IndexSchemaResponse:
    stats = await svc.index_schemas(
        schema_path=body.schema_path,
        database=body.database,
        skip_existing=body.skip_existing,
    )
    return IndexSchemaResponse(
        tables=stats.get("tables", 0),
        columns=stats.get("columns", 0),
        entities=stats.get("entities", 0),
        edges=stats.get("edges", 0),
        domains=stats.get("domains", 0),
        skipped=stats.get("skipped", 0),
    )


@router.post("/initialize")
async def initialize_graph(svc: IndexingService = Depends(_get_service)):
    await svc.initialize_graph()
    return {"status": "initialized"}


@router.get("/stats")
async def get_stats(svc: IndexingService = Depends(_get_service)) -> GraphStatsResponse:
    stats = await svc.get_stats()
    return GraphStatsResponse(
        entities=stats.get("entities", {}),
        episodes=stats.get("episodes", {}),
    )


@router.post("/feedback")
async def store_feedback(
    body: FeedbackRequest,
    svc: IndexingService = Depends(_get_service),
) -> FeedbackResponse:
    episode_id = await svc.record_feedback(
        natural_language=body.natural_language,
        generated_sql=body.generated_sql,
        feedback=body.feedback,
        rating=body.rating,
        corrected_sql=body.corrected_sql,
    )
    return FeedbackResponse(episode_id=episode_id)
