from typing import Any, Dict, List, Optional

from agno.agent import Agent

from src.core.model_factory import create_model
from src.core.types import SchemaContext, ParsedQuery
from src.prompts.manager import get_prompt_manager
from src.tools.graph_tools import GraphSearchTools


def create_schema_discovery_agent(
    graph_tools: GraphSearchTools,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("schema_discovery/instructions.jinja2")

    return Agent(
        name="SchemaDiscovery",
        model=create_model(),
        description="Discovers relevant database schemas using temporal knowledge graph search",
        instructions=[instructions],
        tools=[graph_tools],
        output_schema=SchemaContext,
        markdown=False,
        add_datetime_to_context=True,
        session_id=session_id,
        session_state=session_state or {},
    )


def build_discover_prompt(
    parsed_query: ParsedQuery,
    database: str,
    graph_results: Optional[List[Dict[str, Any]]] = None,
    resolved_terms: Optional[List[Dict[str, str]]] = None,
) -> str:
    pm = get_prompt_manager()
    return pm.render(
        "schema_discovery/discover.jinja2",
        parsed_query=parsed_query,
        database=database,
        graph_results=graph_results or [],
        resolved_terms=resolved_terms or [],
    )

