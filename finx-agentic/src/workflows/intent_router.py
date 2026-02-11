from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Union

from agno.agent import RunOutput
from agno.workflow import Workflow

from src.agents.intent_router import classify_intent, fetch_graph_context, route
from src.core.agentops_tracker import update_trace_metadata
from src.core.cost_tracker import CostTracker
from src.core.intent import RouterResult, UserIntent
from src.tools.graph_tools import GraphSearchTools

logger = logging.getLogger(__name__)


class IntentRouterWorkflow(Workflow):

    def __init__(
        self,
        graph_tools: Optional[GraphSearchTools] = None,
        database: Optional[str] = None,
        available_databases: Optional[List[str]] = None,
        track_cost: bool = True,
        **kwargs,
    ):
        super().__init__(
            name=kwargs.pop("name", "intent_router"),
            description="Intent-aware router workflow with graph context",
            **kwargs,
        )
        self.graph_tools = graph_tools
        self.database = database
        self.available_databases = available_databases or []
        self.track_cost = track_cost

    def run(
        self,
        input: Union[str, List, Dict, Any],
        *,
        stream: Optional[bool] = None,
        **kwargs,
    ) -> Union[RunOutput, Iterator]:
        message = input if isinstance(input, str) else str(input)
        session_state = self.session_state or {}
        conversation_history = session_state.get("conversation_history", [])

        # Update AgentOps trace metadata
        update_trace_metadata({
            "workflow": "intent_router",
            "message": message[:200],
        })

        if not self.graph_tools:
            return RunOutput(content="Graph tools not configured")

        result = route(
            message=message,
            graph_tools=self.graph_tools,
            conversation_history=conversation_history,
            database=self.database,
            available_databases=self.available_databases,
        )

        self.update_session_state(conversation_history=conversation_history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": result.response or result.sql or ""},
        ])

        return RunOutput(content=result.model_dump_json(indent=2))
