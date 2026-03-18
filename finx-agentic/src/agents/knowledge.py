from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from agno.agent import Agent
from agno.db.base import BaseDb

from src.core.llm import create_agno_model_for_agent
from src.core.graph.client import GraphitiClient
from src.knowledge.retrieval import GraphKnowledgeV2
from src.prompts.manager import get_prompt_manager


def _build_knowledge_retriever(knowledge: GraphKnowledgeV2):

    async def _retriever(
        agent: Agent,
        query: str,
        num_documents: Optional[int] = None,
        **kwargs,
    ) -> Optional[List[Dict[str, Any]]]:
        from agno.knowledge.document import Document

        intent_ctx: Dict[str, Any] = {}
        if agent.session_state and isinstance(agent.session_state, dict):
            intent_ctx = agent.session_state.get("intent_analysis", {})

        retrieval_kwargs: Dict[str, Any] = {}
        if intent_ctx:
            if intent_ctx.get("intent"):
                retrieval_kwargs["intent"] = intent_ctx["intent"]
            if intent_ctx.get("domain"):
                retrieval_kwargs["domain"] = intent_ctx["domain"]
            if intent_ctx.get("column_hints"):
                retrieval_kwargs["column_hints"] = intent_ctx["column_hints"]
            weight_hints = intent_ctx.get("weight_hints", {})
            if weight_hints and any(v is not None for v in weight_hints.values()):
                retrieval_kwargs["weight_overrides"] = {
                    k: v for k, v in weight_hints.items() if v is not None
                }

        if num_documents is not None:
            retrieval_kwargs["max_results"] = num_documents

        search_query = intent_ctx.get("english_query") or query

        docs: List[Document] = await knowledge.aretrieve(
            search_query, **retrieval_kwargs
        )
        if not docs:
            return None
        return [doc.to_dict() for doc in docs]

    return _retriever


def create_knowledge_agent(
    graphiti_client: GraphitiClient,
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
    pre_hooks: Optional[List[Callable[..., Any]]] = None,
) -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("knowledge/instructions.jinja2")

    knowledge = GraphKnowledgeV2(
        client=graphiti_client,
        max_results=5,
    )

    return Agent(
        name="Knowledge Agent",
        id="knowledge-agent",
        model=create_agno_model_for_agent("knowledge_agent"),
        description=(
            "Explores the schema knowledge graph. Use this agent when the user "
            "asks about table structures, column meanings, business terms, "
            "relationships between tables, or what data is available. "
            "Also use it to discover relevant schemas before generating SQL."
        ),
        instructions=[instructions],
        knowledge=knowledge,
        knowledge_retriever=_build_knowledge_retriever(knowledge),
        add_knowledge_to_context=True,
        search_knowledge=False,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
        pre_hooks=pre_hooks,
    )