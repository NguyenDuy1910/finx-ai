from typing import Any, Dict, Optional

from agno.agent import Agent
from agno.db.base import BaseDb

from src.core.model_factory import create_model
from src.prompts.manager import get_prompt_manager
from src.tools.graph_tools import GraphSearchTools


def create_knowledge_agent(
    graph_tools: GraphSearchTools,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("knowledge/instructions.jinja2")

    return Agent(
        name="Knowledge",
        model=create_model(),
        description="Explores and manages the schema knowledge graph",
        instructions=[instructions],
        tools=[graph_tools],
        markdown=True,
        add_datetime_to_context=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
        enable_user_memories=db is not None,
        enable_session_summaries=db is not None,
        add_history_to_messages=db is not None,
        num_history_runs=5,
    )
