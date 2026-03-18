from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from agno.os import AgentOS
from agno.os.interfaces.slack import Slack
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agents.company_knowledge import create_company_knowledge_agent
from src.agents.confluence_researcher import create_confluence_researcher_agent
from src.storage.postgres import get_postgres_db
from src.agents.team import build_finx_team
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


def _build_team():
    state = get_app_state()
    database = state.default_database
    pg_db = get_postgres_db()

    finx_team = build_finx_team(
        graphiti_client=state.client,
        database=database,
        output_location=os.getenv("ATHENA_OUTPUT_LOCATION", ""),
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
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
    base_app.include_router(graph_explorer.router, prefix="/api/v1")
    base_app.include_router(indexing.router, prefix="/api/v1")

    finx_team = _build_team()

    pg_db = get_postgres_db()

    confluence_agent = create_confluence_researcher_agent(
        db=pg_db,
    )

    company_knowledge_agent = create_company_knowledge_agent(
        db=pg_db,
    )

    slack_token = os.getenv("SLACK_TOKEN")
    slack_signing_secret = os.getenv("SLACK_SIGNING_SECRET")

    interfaces = []
    if slack_token and slack_signing_secret:
        logger.info("Slack credentials found — enabling Slack interfaces")
        interfaces.append(
            Slack(
                agent=confluence_agent,
                prefix="/slack/confluence",
                token=slack_token,
                signing_secret=slack_signing_secret,
                streaming=False,
                reply_to_mentions_only=False,
                loading_text="Researching...",
                suggested_prompts=[
                    {
                        "title": "Search Confluence",
                        "message": "Search for documentation about our data warehouse",
                    },
                    {
                        "title": "Jira Sprint",
                        "message": "What are the open issues in the current sprint?",
                    },
                ],
            )
        )
        interfaces.append(
            Slack(
                agent=company_knowledge_agent,
                prefix="/slack/knowledge",
                token=slack_token,
                signing_secret=slack_signing_secret,
                streaming=False,
                reply_to_mentions_only=False,
                loading_text="Looking up knowledge...",
                suggested_prompts=[
                    {
                        "title": "Company Policy",
                        "message": "What is our data retention policy?",
                    },
                    {
                        "title": "Business Rules",
                        "message": "What are the KYC requirements for onboarding?",
                    },
                ],
            )
        )
        interfaces.append(
            Slack(
                team=finx_team,
                prefix="/slack/finx",
                token=slack_token,
                signing_secret=slack_signing_secret,
                streaming=False,
                reply_to_mentions_only=False,
                loading_text="Analyzing...",
                suggested_prompts=[
                    {
                        "title": "Data Query",
                        "message": "How many transactions were there this month?",
                    },
                    {
                        "title": "Schema Info",
                        "message": "Which tables contain KYC information?",
                    },
                ],
            )
        )
    else:
        logger.info("Slack credentials not set — Slack interfaces disabled")

    agent_os = AgentOS(
        description="FinX Agentic - multi-agent banking data intelligence system",
        agents=[company_knowledge_agent],
        teams=[finx_team],
        # interfaces=interfaces,
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
