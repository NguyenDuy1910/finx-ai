from typing import Any, Dict, List, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.core.types import ParsedQuery
from src.prompts.manager import get_prompt_manager


def create_query_understanding_agent(
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("query_understanding/instructions.jinja2")

    return Agent(
        name="QueryUnderstanding",
        model=create_model(),
        description="Parses natural language questions into structured query components",
        instructions=[instructions],
        output_schema=ParsedQuery,
        markdown=False,
        add_datetime_to_context=True,
        session_id=session_id,
        session_state=session_state or {},
    )


def build_parse_prompt(
    user_query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    available_entities: Optional[List[Dict[str, str]]] = None,
    recent_patterns: Optional[List[Dict[str, str]]] = None,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "query_understanding/parse.jinja2",
        user_query=user_query,
        conversation_history=conversation_history or [],
        available_entities=available_entities or [],
        recent_patterns=recent_patterns or [],
    )

