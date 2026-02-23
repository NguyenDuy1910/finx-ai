from typing import Any, Callable, Dict, List, Optional, Union

from agno.agent import Agent
from agno.db.base import BaseDb

from src.core.model_factory import create_model_for_agent
from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph_knowledge import GraphKnowledge
from src.prompts.manager import get_prompt_manager


def _build_knowledge_retriever(knowledge: GraphKnowledge):
    """Build a custom knowledge_retriever for embedding-first graph search.

    The retriever extracts intent analysis from ``session_state`` to provide:
      • ``domain`` hint — anchors Layer 1 domain resolution
      • ``column_hints`` — guides Layer 4 column refinement
      • ``weight_overrides`` — steers reranker scoring per intent
      • ``english_query`` — clean English text for better embedding quality

    No keyword search terms are extracted — all discovery happens via vector
    similarity on the query embedding + graph neighborhood traversal.
    """

    async def _retriever(
        agent: Agent,
        query: str,
        num_documents: Optional[int] = None,
        **kwargs,
    ) -> Optional[List[Dict[str, Any]]]:
        from agno.knowledge.document import Document

        # Extract intent analysis from session_state (set by coordinator pre-hook)
        intent_ctx: Dict[str, Any] = {}
        if agent.session_state and isinstance(agent.session_state, dict):
            intent_ctx = agent.session_state.get("intent_analysis", {})

        # Build retrieval kwargs — only what the embedding-first design needs
        retrieval_kwargs: Dict[str, Any] = {}
        if intent_ctx:
            # Intent type → selects reranker weight profile
            if intent_ctx.get("intent"):
                retrieval_kwargs["intent"] = intent_ctx["intent"]

            # Domain hint → anchors L1 domain resolution
            if intent_ctx.get("domain"):
                retrieval_kwargs["domain"] = intent_ctx["domain"]

            # Column hints → guides L4 column refinement
            if intent_ctx.get("column_hints"):
                retrieval_kwargs["column_hints"] = intent_ctx["column_hints"]

            # Weight overrides → steers reranker scoring
            weight_hints = intent_ctx.get("weight_hints", {})
            if weight_hints and any(v is not None for v in weight_hints.values()):
                retrieval_kwargs["weight_overrides"] = {
                    k: v for k, v in weight_hints.items() if v is not None
                }

        if num_documents is not None:
            retrieval_kwargs["max_results"] = num_documents

        # Prefer the English query from intent analysis for better embedding
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

    knowledge = GraphKnowledge(
        client=graphiti_client,
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