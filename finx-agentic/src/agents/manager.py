from typing import Any, Dict, List, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager


def create_manager_agent(
    team: Optional[List[Agent]] = None,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("manager/instructions.jinja2")

    return Agent(
        name="Manager",
        model=create_model(),
        description="Orchestrates the Text2SQL multi-agent system",
        instructions=[instructions],
        markdown=True,
        add_datetime_to_context=True,
        session_id=session_id,
        session_state=session_state or {},
    )


def build_classify_intent_prompt(
    message: str,
    context_summary: str,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "manager/classify_intent.jinja2",
        message=message,
        context_summary=context_summary,
    )


def build_context_summary_prompt(
    message_count: int,
    intent: str,
    has_sql: bool,
    has_results: bool,
    recent_messages: Optional[List[Dict[str, str]]] = None,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "manager/context_summary.jinja2",
        message_count=message_count,
        intent=intent,
        has_sql=has_sql,
        has_results=has_results,
        recent_messages=recent_messages or [],
    )


def build_clarification_prompt(
    message: str,
    reasoning: str,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "manager/clarification_request.jinja2",
        message=message,
        reasoning=reasoning,
    )


def build_help_prompt(message: str) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "manager/help_response.jinja2",
        message=message,
    )

