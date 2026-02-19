import logging
import os
import sys
from contextlib import asynccontextmanager

from agno.os import AgentOS
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.storage.postgres import get_postgres_db
from src.teams.finx_team import build_finx_team
from src.tools.athena_executor import AthenaExecutorTools
from src.web.v1.deps import get_app_state
from src.web.v1.routers import search, graph, health

_original_unraisablehook = sys.unraisablehook


def _quiet_unraisable(args):
    err_msg = getattr(args, "err_msg", None) or ""
    obj = getattr(args, "object", None)
    if "AsyncHttpxClientWrapper.__del__" in err_msg:
        return
    if obj is not None and "AsyncHttpxClientWrapper" in type(obj).__qualname__:
        return
    _original_unraisablehook(args)


sys.unraisablehook = _quiet_unraisable

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = get_app_state()
    await state.initialize()
    yield
    await state.shutdown()


def _build_team():
    state = get_app_state()
    graph_tools = state.sync_graph_tools
    database = state.default_database
    pg_db = get_postgres_db()

    athena_tools = AthenaExecutorTools(
        database=database,
        output_location=os.getenv("ATHENA_OUTPUT_LOCATION", ""),
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    )

    finx_team = build_finx_team(
        graphiti_client=state.client,
        graph_tools=graph_tools,
        athena_tools=athena_tools,
        database=database,
        db=pg_db,
    )

    return finx_team


def create_app() -> FastAPI:
    base_app = FastAPI(
        title="FinX Agentic API",
        version="1.0.0",
        lifespan=lifespan,
    )

    @base_app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    base_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    base_app.include_router(health.router, prefix="/api/v1")
    base_app.include_router(search.router, prefix="/api/v1")
    base_app.include_router(graph.router, prefix="/api/v1")

    finx_team = _build_team()

    agent_os = AgentOS(
        description="FinX Agentic - multi-agent banking data intelligence system",
        teams=[finx_team],
        base_app=base_app,
        on_route_conflict="preserve_base_app",
    )

    return agent_os.get_app()
