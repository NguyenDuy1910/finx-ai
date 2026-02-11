from typing import Any, Dict, List, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager
from src.tools.graph_tools import GraphSearchTools


def create_learning_agent(
    graph_tools: GraphSearchTools,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("learning/instructions.jinja2")

    return Agent(
        name="Learning",
        model=create_model(),
        description="Captures and applies knowledge from query interactions",
        instructions=[instructions],
        tools=[graph_tools],
        markdown=False,
        session_id=session_id,
        session_state=session_state or {},
    )


def build_store_episode_prompt(
    natural_language: str,
    generated_sql: str,
    tables_used: List[str],
    database: str,
    intent: str,
    success: bool,
    user_feedback: Optional[str] = None,
    similar_past_episodes: Optional[List[Dict[str, Any]]] = None,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "learning/store_episode.jinja2",
        natural_language=natural_language,
        generated_sql=generated_sql,
        tables_used=tables_used,
        database=database,
        intent=intent,
        success=success,
        user_feedback=user_feedback,
        similar_past_episodes=similar_past_episodes or [],
    )

