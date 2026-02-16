"""FinX multi-agent team – registered with AgentOS for native API routes.

AgentOS auto-generates:
    POST /teams/finx-assistant/runs   (stream=true → SSE)
    GET  /teams
    GET  /teams/finx-assistant

No custom chat endpoints needed — Agno handles streaming, sessions,
memory, history, and media natively.
"""
from __future__ import annotations

import logging
from typing import Optional

from agno.agent import Agent
from agno.db.base import BaseDb
from agno.team import Team

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager
from src.tools.graph_tools import GraphSearchTools

logger = logging.getLogger(__name__)


def _build_knowledge_agent(
    graph_tools: GraphSearchTools,
    db: Optional[BaseDb] = None,
) -> Agent:
    """Knowledge graph explorer – answers schema/table/relationship questions."""
    pm = get_prompt_manager()
    instructions = pm.render("knowledge/instructions.jinja2")

    return Agent(
        name="Knowledge Agent",
        id="knowledge-agent",
        description=(
            "Explores the schema knowledge graph. Use this agent when the user "
            "asks about table structures, column meanings, business terms, "
            "relationships between tables, or general questions about "
            "what data is available."
        ),
        model=create_model(),
        instructions=[instructions],
        tools=[graph_tools],
        markdown=True,
        add_datetime_to_context=True,
    )


def _build_text2sql_agent(
    graph_tools: GraphSearchTools,
    database: str = "",
    db: Optional[BaseDb] = None,
) -> Agent:
    """Text-to-SQL agent – converts data questions into SQL queries."""
    pm = get_prompt_manager()
    sql_instructions = pm.render("sql_generator/instructions.jinja2")

    return Agent(
        name="Text2SQL Agent",
        id="text2sql-agent",
        description=(
            "Converts natural language data questions into SQL queries for "
            "AWS Athena. Use this agent when the user wants to query actual "
            "data, count records, aggregate numbers, filter rows, or anything "
            "that requires generating and running SQL."
        ),
        model=create_model(),
        instructions=[sql_instructions],
        tools=[graph_tools],
        markdown=True,
        add_datetime_to_context=True,
    )


def _build_schema_explorer_agent(
    graph_tools: GraphSearchTools,
    db: Optional[BaseDb] = None,
) -> Agent:
    """Schema discovery agent – finds relevant tables and join paths."""
    pm = get_prompt_manager()
    instructions = pm.render("schema_discovery/instructions.jinja2")

    return Agent(
        name="Schema Explorer",
        id="schema-explorer",
        description=(
            "Discovers relevant database schemas and finds join paths "
            "between tables. Use this agent when the user asks about "
            "how tables connect, what columns link two entities, "
            "or needs a deep-dive into a specific table's structure."
        ),
        model=create_model(),
        instructions=[instructions],
        tools=[graph_tools],
        markdown=True,
        add_datetime_to_context=True,
    )


def build_finx_team(
    graph_tools: GraphSearchTools,
    database: str = "",
    db: Optional[BaseDb] = None,
) -> Team:
    """Build the FinX multi-agent Team.

    The Team leader model reads the user message and delegates to the
    right member agent based on each member's ``description``.

    Registered with ``AgentOS(teams=[...])`` it exposes:
        POST /teams/finx-assistant/runs
    with native SSE streaming, session persistence, and memory.
    """
    pm = get_prompt_manager()

    # Team-level instructions for the leader/coordinator
    team_instructions = [
        "You are FinX Assistant – a banking data intelligence system.",
        "You coordinate a team of specialist agents to answer user questions.",
        "Route each question to the most appropriate team member based on its nature:",
        "- Knowledge Agent: schema info, table meanings, business terms, relationships",
        "- Text2SQL Agent: data queries that need SQL generation",
        "- Schema Explorer: deep schema discovery, join paths, table connections",
        "If the question is ambiguous, ask the user for clarification before delegating.",
        "Always synthesize the member's response into a clear, user-friendly answer.",
        "Respond in the same language the user uses.",
    ]

    members = [
        _build_knowledge_agent(graph_tools, db=db),
        _build_text2sql_agent(graph_tools, database=database, db=db),
        _build_schema_explorer_agent(graph_tools, db=db),
    ]

    return Team(
        name="FinX Assistant",
        id="finx-assistant",
        description="Multi-agent banking data assistant with knowledge graph, "
                    "Text2SQL, and schema exploration capabilities.",
        model=create_model(),
        members=members,
        instructions=team_instructions,
        # ── Session & Memory ──────────────────────────────────────
        db=db,
        enable_session_summaries=True,
        add_team_history_to_members=True,
        num_history_runs=5,
        # ── Delegation ────────────────────────────────────────────
        determine_input_for_members=True,
        # ── Response ──────────────────────────────────────────────
        markdown=True,
        show_members_responses=False,  # leader synthesizes final response
        # ── Debug ─────────────────────────────────────────────────
        debug_mode=True,
    )
