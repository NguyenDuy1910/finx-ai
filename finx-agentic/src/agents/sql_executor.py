from typing import Any, Dict, List, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager
from src.tools.athena_executor import AthenaExecutorTools
from src.tools.graph_tools import GraphSearchTools


def create_sql_executor_agent(
    athena_tools: AthenaExecutorTools,
    graph_tools: Optional[GraphSearchTools] = None,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("sql_executor/instructions.jinja2")

    tools: List[Any] = [athena_tools]
    if graph_tools:
        tools.append(graph_tools)

    return Agent(
        name="SQL Executor Agent",
        id="sql-executor-agent",
        model=create_model(),
        description=(
            "Executes validated SQL queries on AWS Athena and returns results. "
            "Use this agent ONLY after the Validation Agent confirms the SQL "
            "is valid. It presents results in readable tables with insights."
        ),
        instructions=[instructions],
        tools=tools,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
    )
