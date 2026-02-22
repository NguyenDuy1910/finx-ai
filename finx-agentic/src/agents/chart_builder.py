from typing import Any, Dict, Optional

from agno.agent import Agent
from agno.db.base import BaseDb

from src.core.model_factory import create_model_for_agent
from src.prompts.manager import get_prompt_manager
from src.tools.chart_builder import ChartBuilderTools


def create_chart_builder_agent(
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("chart_builder/instructions.jinja2")

    chart_tools = ChartBuilderTools()

    return Agent(
        name="Chart Builder Agent",
        id="chart-builder-agent",
        model=create_model_for_agent("chart_builder_agent"),
        description=(
            "Analyzes SQL query results and produces chart/dashboard specifications. "
            "Use this agent AFTER the SQL Generator Agent has successfully executed "
            "a query and returned data. It selects the best chart type (bar, line, "
            "pie, metric, etc.) and returns a structured JSON chart spec for the "
            "frontend to render."
        ),
        instructions=[instructions],
        tools=[chart_tools],
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
    )
