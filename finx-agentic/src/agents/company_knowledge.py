from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

from agno.agent import Agent
from agno.db.base import BaseDb

from src.core.llm import create_agno_model_for_agent
from src.knowledge.retrieval.confluence_knowledge import ConfluenceKnowledge
from src.knowledge.retrieval.reranker import DocumentReranker
from src.prompts.manager import get_prompt_manager

logger = logging.getLogger(__name__)

_CITATIONS_STATE_KEY = "_citations"

# Chunk kinds that represent visual/file artifacts the UI can render inline
_ARTIFACT_KINDS = {"image_caption", "attachment", "chart_summary", "diagram_summary"}

# MIME prefixes for inline-renderable media
_IMAGE_MIMES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml")

# MIME substrings for spreadsheets
_SPREADSHEET_MIMES = ("spreadsheet", "excel", "csv", "vnd.ms-excel")

# MIME substrings for documents
_DOCUMENT_MIMES = ("wordprocessingml", "msword", "presentationml", "ms-powerpoint", "opendocument")


def _build_knowledge_retriever(knowledge: ConfluenceKnowledge) -> Callable:
    """Build a retriever that stores citations (with artifact metadata) in session_state."""

    async def _retriever(
        agent: Agent,
        query: str,
        num_documents: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[List[Dict[str, Any]]]:
        from agno.knowledge.document import Document

        retrieval_kwargs: Dict[str, Any] = {}

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

        citations: list[dict[str, Any]] = []
        existing_count = len((agent.session_state or {}).get(_CITATIONS_STATE_KEY) or [])

        for i, doc in enumerate(docs):
            meta = doc.meta_data or {}
            source_url = meta.get("source_url") or None
            chunk_kind = meta.get("chunk_kind", "")
            mime_type = meta.get("mime_type", "")
            artifact_uri = meta.get("artifact_uri", "")
            source_type_raw = meta.get("source_type", "")
            parent_content_id = meta.get("parent_content_id", "")
            space_key = meta.get("space_key", "")
            section_path: list[str] = meta.get("section_path", [])

            # Derive parent page title from section_path
            # section_path looks like: ["Space: X", "Page: Title", "Attachment: file.png"]
            parent_title = ""
            for seg in section_path:
                if seg.startswith("Page:"):
                    parent_title = seg[5:].strip()

            citation: dict[str, Any] = {
                "id": meta.get("chunk_id") or meta.get("doc_id") or "",
                "title": doc.name or meta.get("doc_title", ""),
                "source_type": meta.get("source_system") or "knowledge",
                "snippet": (doc.content or "")[:300],
                "content": doc.content or "",
                "chunk_kind": chunk_kind,
                "space_key": space_key,
                "external_id": meta.get("external_id", ""),
                "url": source_url,
                "score": meta.get("rerank_score"),
                "index": existing_count + i + 1,
                # Source classification for frontend rendering
                "content_source_type": source_type_raw,
            }

            # Parent Confluence page context — crucial for attachments
            if parent_content_id:
                citation["parent_content_id"] = parent_content_id
                if parent_title:
                    citation["parent_title"] = parent_title

            # Attach artifact metadata so the UI can render images/files inline
            if artifact_uri:
                citation["artifact_uri"] = artifact_uri
            if mime_type:
                citation["mime_type"] = mime_type

            # Mark as artifact if chunk_kind matches, source_type is attachment,
            # or artifact_uri is present (local file was cached during ingestion)
            is_artifact = (
                chunk_kind in _ARTIFACT_KINDS
                or source_type_raw == "attachment"
                or bool(artifact_uri)
            )
            if is_artifact:
                citation["is_artifact"] = True
                if mime_type.startswith(_IMAGE_MIMES):
                    citation["artifact_type"] = "image"
                elif mime_type.startswith("application/pdf"):
                    citation["artifact_type"] = "pdf"
                elif any(s in mime_type for s in _SPREADSHEET_MIMES):
                    citation["artifact_type"] = "spreadsheet"
                elif any(s in mime_type for s in _DOCUMENT_MIMES):
                    citation["artifact_type"] = "document"
                else:
                    citation["artifact_type"] = "file"

            citations.append(citation)

        # Accumulate citations (dedup by id)
        if agent.session_state is not None:
            existing = agent.session_state.get(_CITATIONS_STATE_KEY) or []
            seen_ids = {c["id"] for c in existing if c["id"]}
            new_citations = [c for c in citations if not c["id"] or c["id"] not in seen_ids]
            agent.session_state[_CITATIONS_STATE_KEY] = existing + new_citations
        else:
            agent.session_state = {_CITATIONS_STATE_KEY: citations}

        # Embed citation metadata in retrieval result for streaming citation events
        doc_dicts = [doc.to_dict() for doc in docs]
        valid = [c for c in citations if c.get("title") or c.get("snippet")]
        if valid and doc_dicts:
            citations_block = json.dumps(valid, ensure_ascii=False)
            last = doc_dicts[-1]
            last["content"] = (
                last.get("content", "")
                + f"\n\n<retrieval-citations>{citations_block}</retrieval-citations>"
            )

        return doc_dicts

    return _retriever


def _emit_citations_hook(run_output: Any, agent: Agent) -> None:
    """Post-hook: append <citations> JSON block for the frontend to parse and render."""
    content = run_output.content
    if not isinstance(content, str):
        return

    citations: List[Dict[str, Any]] = []
    if agent.session_state:
        citations = agent.session_state.get(_CITATIONS_STATE_KEY) or []

    valid = [c for c in citations if c.get("title") or c.get("snippet")]
    if not valid:
        return

    run_output.content = content + f"\n\n<citations>{json.dumps(valid, ensure_ascii=False)}</citations>"
    logger.debug("_emit_citations_hook: appended %d citations", len(valid))

    agent.session_state[_CITATIONS_STATE_KEY] = []


def create_company_knowledge_agent(
    session_id: Optional[str] = None,
    session_state: Optional[Dict[str, Any]] = None,
    db: Optional[BaseDb] = None,
) -> Agent:
    """Create the company knowledge assistant agent.

    Knowledge-only agent — no MCP tools. Retrieves from the Qdrant vector store
    and returns answers with citations including artifact metadata for inline
    image/file rendering in the UI.
    """
    pm = get_prompt_manager()
    instructions = pm.render("company_knowledge/instructions.jinja2")

    reranker = DocumentReranker()
    knowledge = ConfluenceKnowledge(
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        collection_name=os.getenv("QDRANT_COLLECTION", "finx_knowledge"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        reranker=reranker,
        top_k=30,
        rerank_top_n=8,
    )

    return Agent(
        name="Company Knowledge",
        id="company-knowledge",
        model=create_agno_model_for_agent("company_knowledge_agent"),
        description=(
            "Internal company knowledge assistant. Answers questions from "
            "Confluence, Jira, and internal documents stored in the knowledge base. "
            "Returns answers with citations, images, and file attachments."
        ),
        instructions=[instructions],
        knowledge=knowledge,
        knowledge_retriever=_build_knowledge_retriever(knowledge),
        # Agentic RAG: agent decides WHEN to search (not auto-dump all results)
        add_knowledge_to_context=False,
        search_knowledge=True,
        # ReAct reasoning: think about intent before searching/answering
        reasoning=True,
        reasoning_min_steps=1,
        reasoning_max_steps=2,
        add_history_to_context=True,
        num_history_runs=4,
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=True,
        session_id=session_id,
        session_state=session_state or {},
        db=db,
        post_hooks=[_emit_citations_hook],
    )
