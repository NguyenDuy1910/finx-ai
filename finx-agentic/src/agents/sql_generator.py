from typing import Any, Dict, Optional

from agno.agent import Agent
from agno.db.base import BaseDb

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager
from src.agents.hooks.sql_auto_execute import (
    AthenaDirectExecutor,
    create_sql_auto_execute_hook,
)


def create_sql_generator_agent(
    database: str = "",
    output_location: str = "",
    region_name: str = "ap-southeast-1",
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("sql_generator/instructions.jinja2")

    executor = AthenaDirectExecutor(
        database=database,
        output_location=output_location,
        region_name=region_name,
    )

    return Agent(
        name="SQL Generator Agent",
        id="sql-generator-agent",
        model=create_model(),
        description=(
            "Converts natural language data questions into SQL queries for "
            "AWS Athena. Generates SQL, the system auto-validates and executes "
            "it, then the agent presents the results. "
            "Use this agent when the user wants to query data, count records, "
            "aggregate numbers, filter rows, or run SQL."
        ),
        instructions=[instructions],
        tools=[],
        post_hooks=[create_sql_auto_execute_hook(executor)],
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
    )

