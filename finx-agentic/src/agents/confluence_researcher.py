from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from agno.agent import Agent
from agno.db.base import BaseDb
from agno.tools.mcp import MCPTools

from src.core.llm import create_agno_model_for_agent
from src.prompts.manager import get_prompt_manager
from src.tools.mcp_atlassian_tools import create_atlassian_mcp_tools_auto

logger = logging.getLogger(__name__)


def create_confluence_researcher_agent(
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
    confluence_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_key: Optional[str] = None,
    pre_hooks: Optional[List[Callable[..., Any]]] = None,
    mcp_tools: Optional[MCPTools] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("confluence_researcher/instructions_mcp.jinja2")

    if mcp_tools is None:
        mcp_tools = create_atlassian_mcp_tools_auto(
            confluence_url=confluence_url or os.getenv("CONFLUENCE_URL", ""),
            confluence_username=confluence_username or os.getenv("CONFLUENCE_USERNAME", ""),
            confluence_api_token=confluence_api_key or os.getenv("CONFLUENCE_API_KEY", ""),
        )

    return Agent(
        name="Confluence Researcher",
        id="confluence-researcher",
        model=create_agno_model_for_agent("confluence_researcher"),
        description=(
            "Deep-dive research agent for Confluence knowledge bases. "
            "Use this agent when you need to search company documentation, "
            "retrieve technical specs, find decision records, synthesize "
            "information from multiple pages, or create research reports."
        ),
        instructions=[instructions],
        tools=[mcp_tools],
        add_history_to_context=True,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
        pre_hooks=pre_hooks,
    )
