from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

from agno.agent import Agent
from agno.db.base import BaseDb
from agno.tools.mcp import MCPTools

from src.core.llm import create_agno_model_for_agent
from src.knowledge.retrieval.qdrant_knowledge import QdrantKnowledge
from src.knowledge.retrieval.reranker import DocumentReranker
from src.prompts.manager import get_prompt_manager
from src.tools.mcp_atlassian_tools import create_confluence_mcp_tools

logger = logging.getLogger(__name__)

# Key used to store retrieved citation docs in session_state
_CITATIONS_STATE_KEY = "_citations"


def _build_knowledge_retriever(knowledge: QdrantKnowledge) -> Callable:
    """Build a custom retriever that passes optional filters from session_state
    and stores retrieved documents as citations in session_state for post-hook use.
    """

    async def _retriever(
        agent: Agent,
        query: str,
        num_documents: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[List[Dict[str, Any]]]:
        from agno.knowledge.document import Document

        retrieval_kwargs: Dict[str, Any] = {}

        # Pull optional filter hints from session_state (set by caller if needed)
        state: Dict[str, Any] = agent.session_state or {}
        if language := state.get("language"):
            retrieval_kwargs["language"] = language
        if domain := state.get("domain"):
            retrieval_kwargs["domain"] = domain
        if doc_type := state.get("document_type"):
            retrieval_kwargs["document_type"] = doc_type
        if num_documents is not None:
            retrieval_kwargs["rerank_top_n"] = num_documents

        docs: List[Document] = await knowledge.aretrieve(query, **retrieval_kwargs)
        if not docs:
            return None

        # Store citation metadata in session_state for the post-hook
        citations = []
        existing_count = len((agent.session_state or {}).get(_CITATIONS_STATE_KEY) or [])
        for i, doc in enumerate(docs):
            meta = doc.meta_data or {}
            citation = {
                "id": doc.id or doc.content_id or "",
                "title": doc.name or meta.get("title", ""),
                "source_type": meta.get("source", meta.get("source_type", "qdrant")),
                "snippet": doc.content[:300] if doc.content else "",
                "content": doc.content or "",
                "page": meta.get("page_number", meta.get("page", None)),
                "url": meta.get("url", meta.get("source_url", None)),
                "score": doc.reranking_score,
                "index": existing_count + i + 1,  # 1-based, continues from prior retrievals
            }
            citations.append(citation)

        # Accumulate citations across multiple retrieval calls in one run
        if agent.session_state is not None:
            existing = agent.session_state.get(_CITATIONS_STATE_KEY) or []
            # Deduplicate by id
            seen_ids = {c["id"] for c in existing if c["id"]}
            new_citations = [c for c in citations if not c["id"] or c["id"] not in seen_ids]
            agent.session_state[_CITATIONS_STATE_KEY] = existing + new_citations
        else:
            agent.session_state = {_CITATIONS_STATE_KEY: citations}

        return [doc.to_dict() for doc in docs]

    return _retriever


def _emit_citations_hook(run_output: Any, agent: Agent) -> None:
    """Post-hook: append a <citations> JSON block to the run output content.

    The Next.js route will parse this block, emit structured citation events
    to the frontend, and strip the block from displayed text.
    """
    content = run_output.content
    if not isinstance(content, str):
        return

    citations: List[Dict[str, Any]] = []
    if agent.session_state:
        citations = agent.session_state.get(_CITATIONS_STATE_KEY) or []

    if not citations:
        return

    # Filter out empty entries
    valid_citations = [c for c in citations if c.get("title") or c.get("snippet")]
    if not valid_citations:
        return

    citations_json = json.dumps(valid_citations, ensure_ascii=False)
    run_output.content = content + f"\n\n<citations>{citations_json}</citations>"
    logger.debug("_emit_citations_hook: appended %d citations", len(valid_citations))

    # Clear citations from session_state so they don't accumulate across turns
    agent.session_state[_CITATIONS_STATE_KEY] = []


def create_company_knowledge_agent(
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
    mcp_tools: Optional[MCPTools] = None,
) -> Agent:
    """Create the company knowledge assistant agent.

    Args:
        session_id: Agno session identifier for conversation persistence.
        session_state: Initial session state dict (e.g. {"language": "vi"}).
        db: PostgresDb instance for conversation memory storage.
        mcp_tools: Pre-built MCPTools instance (built from env vars if None).

    Returns:
        Configured Agno Agent instance.
    """
    pm = get_prompt_manager()
    instructions = pm.render("company_knowledge/instructions.jinja2")

    reranker = DocumentReranker()
    knowledge = QdrantKnowledge(
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        collection_name=os.getenv("QDRANT_COLLECTION", "finx_knowledge"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        reranker=reranker,
        top_k=20,
        rerank_top_n=5,
    )

    if mcp_tools is None:
        try:
            mcp_tools = create_confluence_mcp_tools(
                confluence_url=os.getenv("CONFLUENCE_URL", ""),
                confluence_username=os.getenv("CONFLUENCE_USERNAME", ""),
                confluence_api_token=os.getenv("CONFLUENCE_API_KEY", ""),
            )
        except Exception as exc:
            logger.warning("Could not create Confluence MCP tools: %s. Agent will rely on Qdrant only.", exc)
            mcp_tools = None

    tools = [mcp_tools] if mcp_tools is not None else []

    return Agent(
        name="Company Knowledge",
        id="company-knowledge",
        model=create_agno_model_for_agent("company_knowledge_agent"),
        description=(
            "Internal company knowledge assistant. Answers questions from Confluence "
            "documentation, company policies, procedures, business rules, and project "
            "knowledge. Falls back to live Confluence search when needed."
        ),
        instructions=[instructions],
        knowledge=knowledge,
        knowledge_retriever=_build_knowledge_retriever(knowledge),
        # Pre-inject top-k results AND allow agent to search again when it needs more
        add_knowledge_to_context=True,
        search_knowledge=True,
        tools=tools,
        add_history_to_context=True,
        num_history_runs=10,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
        post_hooks=[_emit_citations_hook],
    )
