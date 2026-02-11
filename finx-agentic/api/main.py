from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

# ── Langtrace observability ───────────────────────────────────────────
# Docs: https://docs-v1.agno.com/observability/langtrace
from langtrace_python_sdk import langtrace

langtrace.init(api_key=os.getenv("LANGTRACE_API_KEY"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_memory
from api.routes import agent, graph, health

# ── AgentOps observability ────────────────────────────────────────────
# Docs: https://docs.agentops.ai/v2/introduction
# Must be initialised AFTER agno imports to avoid circular import issues.
from src.core.agentops_tracker import init_agentops

init_agentops(tags=["finx-agentic", "api"])

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mem = get_memory()
    await mem.initialize()
    logger.info("FinX API ready")
    yield
    await mem.close()
    # End AgentOps session on shutdown
    from src.core.agentops_tracker import end_session
    end_session(end_state="Success", end_state_reason="API shutdown")
    logger.info("FinX API shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="FinX Agentic API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(graph.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")

    return app


app = create_app()
