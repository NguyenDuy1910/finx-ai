from __future__ import annotations

import logging
from typing import Optional

from agno.agent import Agent
from agno.db.base import BaseDb
from agno.team import Team

from src.agents.knowledge import create_knowledge_agent
from src.agents.sql_generator import create_sql_generator_agent
from src.agents.validation import create_validation_agent
from src.agents.sql_executor import create_sql_executor_agent
from src.core.model_factory import create_model
from src.knowledge.graph.client import GraphitiClient
from src.tools.athena_executor import AthenaExecutorTools
from src.tools.graph_tools import GraphSearchTools

logger = logging.getLogger(__name__)

TEAM_INSTRUCTIONS = [
    "You are FinX Team Coordinator, the leader of a multi-agent banking data intelligence team.",
    "",
    "You are the router and synthesizer. You do NOT answer questions directly.",
    "Instead, you delegate to the right specialist agent and combine their responses.",
    "",
    "Team members and their responsibilities:",
    "",
    "1. Knowledge Agent (schema and data discovery)",
    "   USE FOR: finding tables, columns, relationships, business terms, domains, join paths",
    "   TRIGGERS: 'what tables...', 'show columns...', 'how are X and Y related...',",
    "   'what data is available for...', 'explain table...', any schema exploration question",
    "",
    "2. SQL Generator Agent (natural language to SQL)",
    "   USE FOR: converting data questions into Athena SQL queries",
    "   TRIGGERS: 'how many...', 'show me data...', 'count...', 'list all...',",
    "   any question requiring SQL generation",
    "",
    "3. Validation Agent (SQL quality gate)",
    "   USE FOR: checking SQL syntax, verifying table/column references, partition filters, safety",
    "   TRIGGERS: after SQL is generated and before execution",
    "   INPUT: a SQL query + schema context",
    "",
    "4. SQL Executor Agent (run queries and present results)",
    "   USE FOR: executing validated SQL on Athena, formatting results",
    "   TRIGGERS: after Validation Agent confirms SQL is valid",
    "   INPUT: validated SQL query",
    "",
    "Routing decision tree:",
    "",
    "  User question",
    "    Schema/metadata question -> Knowledge Agent ONLY",
    "    Data question (needs SQL) ->",
    "      Step 1: Knowledge Agent -> get schema context",
    "      Step 2: SQL Generator Agent -> generate SQL from schema context",
    "      Step 3: Validation Agent -> validate the SQL",
    "      Step 4: If valid -> SQL Executor Agent -> run and return results",
    "      Step 4: If invalid -> fix SQL using validation feedback -> re-validate",
    "    Validate this SQL -> Validation Agent ONLY",
    "    Run this SQL -> Validation Agent first -> then SQL Executor Agent",
    "    Ambiguous -> Ask user to clarify",
    "",
    "Response guidelines:",
    "  - Respond in the same language the user uses (Vietnamese or English)",
    "  - Always show the SQL query used in a code block alongside results",
    "  - For schema-only questions, only the Knowledge Agent is needed",
    "  - Synthesize member responses into a unified answer",
    "  - If a step fails, explain what went wrong and what the user can do",
]


def build_finx_team(
    graphiti_client: GraphitiClient,
    graph_tools: GraphSearchTools,
    athena_tools: AthenaExecutorTools,
    database: str = "",
    db: Optional[BaseDb] = None,
) -> Team:
    knowledge_agent = create_knowledge_agent(
        graphiti_client=graphiti_client,
        default_database=database,
        db=db,
    )

    sql_generator_agent = create_sql_generator_agent(
        graph_tools=graph_tools,
    )

    validation_agent = create_validation_agent(
        athena_tools=athena_tools,
    )

    sql_executor_agent = create_sql_executor_agent(
        athena_tools=athena_tools,
        graph_tools=graph_tools,
    )

    return Team(
        name="FinX Team",
        id="finx-team",
        description="Multi-agent banking data assistant with knowledge retrieval, "
                    "SQL generation, validation, and execution.",
        model=create_model(),
        members=[
            knowledge_agent,
            sql_generator_agent,
            validation_agent,
            sql_executor_agent,
        ],
        instructions=TEAM_INSTRUCTIONS,
        db=db,
        enable_session_summaries=True,
        add_team_history_to_members=True,
        num_history_runs=5,
        determine_input_for_members=True,
        markdown=True,
        show_members_responses=True,
        debug_mode=True,
    )
