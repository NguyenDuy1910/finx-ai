from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from agno.os import AgentOS
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agents.executive_agent import create_executive_knowledge_agent
from src.storage.postgres import get_postgres_db
from src.web.v1.deps import get_app_state
from src.web.v1.routers import graph, graph_explorer, health, indexing, search

_original_unraisablehook = sys.unraisablehook


def _quiet_unraisable(args):  # noqa: ANN001
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
    base_app.include_router(graph_explorer.router, prefix="/api/v1")
    base_app.include_router(indexing.router, prefix="/api/v1")

    pg_db = get_postgres_db()

    executive_agent = create_executive_knowledge_agent(
        db=pg_db,
    )

    agent_os = AgentOS(
        description="FinX Agentic - multi-agent banking data intelligence system",
        agents=[executive_agent],
        base_app=base_app,
        on_route_conflict="preserve_base_app",
    )

    return agent_os.get_app()


app = create_app()

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run(
        "src.web.app:app",
        host=host,
        port=port,
        reload=True,
    )
