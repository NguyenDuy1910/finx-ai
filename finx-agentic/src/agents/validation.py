from typing import Any, Dict, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager
from src.tools.athena_executor import AthenaExecutorTools


def create_validation_agent(
    athena_tools: Optional[AthenaExecutorTools] = None,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("validation/instructions.jinja2")

    tools = [athena_tools] if athena_tools else []

    return Agent(
        name="Validation Agent",
        id="validation-agent",
        model=create_model(),
        description=(
            "Validates SQL queries for correctness and safety. Use this agent "
            "after SQL is generated to check syntax, verify table/column names, "
            "ensure partition filters exist, and catch dangerous operations."
        ),
        instructions=[instructions],
        tools=tools,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
    )

