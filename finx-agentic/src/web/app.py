import logging
import sys
from contextlib import asynccontextmanager

from agno.agent import Agent
from agno.os import AgentOS
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager
from src.storage.postgres import get_postgres_db
from src.teams.finx_team import build_finx_team
from src.web.v1.deps import get_app_state
from src.web.v1.routers import search, graph, health
from src.workflows.intent_router import IntentRouterWorkflow
from src.workflows.text2sql import Text2SQLWorkflow

_original_unraisablehook = sys.unraisablehook


def _quiet_unraisable(args):
    """Silently swallow the known httpx __del__ AttributeError."""
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


def _build_agents_and_workflows():
    """Build Agno agents, workflows & teams for AgentOS registration.

    AgentOS auto-generates these endpoints (zero custom code):
        POST /agents/<agent-id>/runs      – run / stream an agent
        POST /workflows/<workflow-id>/runs – run a workflow
        POST /teams/<team-id>/runs        – run multi-agent team (SSE)
        GET  /agents                       – list agents
        GET  /workflows                    – list workflows
        GET  /teams                        – list teams
        GET  /sessions                     – list sessions
        …and more (memories, knowledge, evals, metrics)
    """
    state = get_app_state()
    graph_tools = state.sync_graph_tools
    database = state.default_database
    pg_db = get_postgres_db()
    pm = get_prompt_manager()

    # ── Knowledge Agent (standalone – backward compat) ────────────────
    knowledge_instructions = pm.render("knowledge/instructions.jinja2")
    knowledge_agent = Agent(
        name="Knowledge Agent",
        model=create_model(),
        instructions=[knowledge_instructions],
        tools=[graph_tools],
        markdown=True,
        add_datetime_to_context=True,
        db=pg_db,
        enable_session_summaries=True,
        add_history_to_context=True,
        num_history_runs=5,
        debug_mode=True,
    )

    # ── Intent Router Workflow ────────────────────────────────────────
    intent_router_workflow = IntentRouterWorkflow(
        id="intent-router",
        graph_tools=graph_tools,
        database=database,
        available_databases=[database] if database else [],
        db=pg_db,
    )

    # ── Text2SQL Workflow ─────────────────────────────────────────────
    text2sql_workflow = Text2SQLWorkflow(
        id="text2sql",
        database=database,
        graph_tools=graph_tools,
        max_retries=2,
        track_cost=True,
        db=pg_db,
    )

    # ── FinX Multi-Agent Team ─────────────────────────────────────────
    finx_team = build_finx_team(
        graph_tools=graph_tools,
        database=database,
        db=pg_db,
    )

    agents = [knowledge_agent]
    workflows = [intent_router_workflow, text2sql_workflow]
    teams = [finx_team]

    return agents, workflows, teams


def create_app() -> FastAPI:
    # 1. Build a lightweight FastAPI app with domain-specific routes only
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

    # Domain-specific routes that AgentOS doesn't cover
    base_app.include_router(health.router, prefix="/api/v1")
    base_app.include_router(search.router, prefix="/api/v1")
    base_app.include_router(graph.router, prefix="/api/v1")

    # 2. Register agents, workflows & teams with AgentOS
    #    AgentOS merges its native routes into the base_app:
    #      POST /agents/{agent_id}/runs     (stream=true for SSE)
    #      POST /workflows/{workflow_id}/runs
    #      POST /teams/{team_id}/runs       (multi-agent SSE)
    #      GET  /agents, /workflows, /teams, /sessions, …
    agents, workflows, teams = _build_agents_and_workflows()

    agent_os = AgentOS(
        description="FinX Agentic – multi-agent NL→SQL & knowledge system",
        agents=agents,
        workflows=workflows,
        teams=teams,
        base_app=base_app,
        on_route_conflict="preserve_base_app",
    )

    return agent_os.get_app()
