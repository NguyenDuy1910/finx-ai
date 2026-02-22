from typing import Any, Dict, Optional

from agno.agent import Agent
from agno.db.base import BaseDb

from src.core.model_factory import create_model_for_agent
from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph_knowledge import GraphKnowledge
from src.prompts.manager import get_prompt_manager


def create_knowledge_agent(
    graphiti_client: GraphitiClient,
    default_database: Optional[str] = None,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("knowledge/instructions.jinja2")

    knowledge = GraphKnowledge(
        client=graphiti_client,
        default_database=default_database,
        max_results=5,
    )

    return Agent(
        name="Knowledge Agent",
        id="knowledge-agent",
        model=create_model_for_agent("knowledge_agent"),
        description=(
            "Explores the schema knowledge graph. Use this agent when the user "
            "asks about table structures, column meanings, business terms, "
            "relationships between tables, or what data is available. "
            "Also use it to discover relevant schemas before generating SQL."
        ),
        instructions=[instructions],
        knowledge=knowledge,
        add_knowledge_to_context=True,
        search_knowledge=False,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
    )