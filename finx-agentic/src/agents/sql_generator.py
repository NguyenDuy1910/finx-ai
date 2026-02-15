from typing import Any, Dict, List, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.core.types import GeneratedSQL, SchemaContext
from src.prompts.manager import get_prompt_manager
from src.tools.graph_tools import GraphSearchTools


def create_sql_generator_agent(
    graph_tools: Optional[GraphSearchTools] = None,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("sql_generator/instructions.jinja2")

    tools = [graph_tools] if graph_tools else []

    return Agent(
        name="SQLGenerator",
        model=create_model(),
        description="Generates partition-aware SQL queries for AWS Athena",
        instructions=[instructions],
        tools=tools,
        output_schema=GeneratedSQL,
        markdown=False,
        add_datetime_to_context=True,
        session_id=session_id,
        session_state=session_state or {},
    )


def build_generate_sql_prompt(
    user_query: str,
    schema_context: Optional[SchemaContext] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "sql_generator/generate_sql.jinja2",
        user_query=user_query,
        schema_context=schema_context.model_dump_json(indent=2) if schema_context else None,
        conversation_history=conversation_history or [],
    )


def build_retry_prompt(
    user_query: str,
    previous_sql: str,
    error_message: str,
    schema_context: Optional[SchemaContext] = None,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "sql_generator/retry_with_error.jinja2",
        user_query=user_query,
        previous_sql=previous_sql,
        error_message=error_message,
        schema_context=schema_context.model_dump_json(indent=2) if schema_context else None,
    )

