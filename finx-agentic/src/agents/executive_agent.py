"""Factory for the Company Knowledge agent — Confluence / Jira / internal docs."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from agno.agent import Agent
from agno.db.base import BaseDb

from src.agents.hooks.citations_hook import emit_citations_hook
from src.core.llm import _agent_provider
from src.knowledge.retrieval.vector_knowledge import VectorKnowledge, VectorKnowledgeConfig
from src.prompts.manager import get_prompt_manager

_DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "finx_knowledge")


def create_executive_knowledge_agent(
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
    *,
    knowledge: Optional[VectorKnowledge] = None,
) -> Agent:
    shared_state: Dict[str, Any] = session_state or {}

    if knowledge is None:
        knowledge = VectorKnowledge(
            config=VectorKnowledgeConfig(collection_name=_DEFAULT_COLLECTION),
            session_state=shared_state,
        )
    elif knowledge.session_state is None:
        knowledge.session_state = shared_state

    pm = get_prompt_manager()
    instructions = pm.render("executive_knowledge/instructions.jinja2")

    return Agent(
        name="Executive Knowledge",
        id="company-knowledge",
        model=_agent_provider("executive_knowledge_agent"),
        description=(
            "Internal executive knowledge assistant. Answers questions from "
            "Confluence, Jira, and internal documents stored in the knowledge base. "
            "Returns answers with citations, images, and file attachments."
        ),
        instructions=[instructions],
        # ── Knowledge: agentic RAG — LLM calls search tool when needed
        knowledge=knowledge,
        search_knowledge=True,
        add_knowledge_to_context=False,
        tools=[],
        tool_call_limit=3,
        reasoning=False,
        add_history_to_context=True,
        num_history_runs=2,
        num_history_messages=6,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=bool(os.getenv("DEBUG", "")),
        session_id=session_id,
        session_state=shared_state,
        db=db,
        post_hooks=[emit_citations_hook],
    )
