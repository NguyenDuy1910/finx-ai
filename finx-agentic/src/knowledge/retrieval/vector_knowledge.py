"""VectorKnowledge — Agno KnowledgeProtocol backed by Qdrant + advanced postprocess pipeline."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, List

from agno.knowledge.document import Document

from src.core.models.retrieval import RetrievedDocument
from src.knowledge.retrieval.confluence_knowledge import (
    RetrievalStore,
    scored_point_to_document,
)
from src.knowledge.retrieval.filters import build_qdrant_filter, build_search_params_filter
from src.knowledge.retrieval.postprocess.cleaner import clean
from src.knowledge.retrieval.postprocess.context_packer import (
    blocks_to_documents,
    pack_blocks,
)
from src.knowledge.retrieval.postprocess.deduplicator import (
    deduplicate_by_content,
    deduplicate_hits_by_doc,
)
from src.knowledge.retrieval.postprocess.expander import expand_groups
from src.knowledge.retrieval.postprocess.grouper import group_by_source
from src.knowledge.retrieval.postprocess.reranker import rerank_blocks
from src.knowledge.retrieval.utils.citations import (
    CITATIONS_STATE_KEY,
    accumulate_citations,
)
from src.models.retrieval_context import RetrievalContext

log = logging.getLogger(__name__)


@dataclass
class SearchParams:
    """Per-call overrides the agent can pass through the tool to guide retrieval.

    All fields are optional — unset fields fall back to ``VectorKnowledgeConfig``.
    """

    source_type: str | None = None
    """Filter by source system, e.g. ``"confluence"`` or ``"jira"``."""

    space_key: str | None = None
    """Confluence space key (e.g. ``"TECH"``) or Jira project key to scope search."""

    top_k: int | None = None
    """Number of final results to return (default: config.rerank_top_n, max: 10)."""


@dataclass
class VectorKnowledgeConfig:
    """Tuning knobs for the retrieval pipeline."""

    collection_name: str = "finx_knowledge"
    dense_vector_name: str = ""  # empty = default/unnamed vector
    embedding_model: str = ""

    # search
    candidate_limit: int = 40
    top_k: int = 8

    # dedup
    max_hits_per_doc: int = 3
    content_dedup_threshold: float = 0.6

    # grouping / expansion
    max_groups: int = 10
    expansion_policy: str = "standard"
    max_blocks: int = 8

    # reranking
    rerank_top_n: int = 6

    # packing
    max_pack_blocks: int = 6
    max_total_chars: int = 16_000
    max_block_chars: int = 4_000


class VectorKnowledge:
    """Agno KnowledgeProtocol implementation with full postprocess pipeline.

    Modes:
        - Agentic RAG: ``search_knowledge=True`` → LLM calls ``search_knowledge_base`` tool
        - Context injection: ``add_knowledge_to_context=True`` → auto-inject via ``retrieve()``
    """

    def __init__(
        self,
        *,
        store: RetrievalStore | None = None,
        retrieval_context: RetrievalContext | None = None,
        config: VectorKnowledgeConfig | None = None,
        session_state: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.retrieval_context = retrieval_context
        self.config = config or VectorKnowledgeConfig()
        self.session_state = session_state
        self._embedder: Any | None = None
        self._qdrant: Any | None = None

    def _get_embedder(self) -> Any:
        """Lazy-init the async embedder."""
        if self._embedder is None:
            from src.providers.embedder import Embedder
            model = self.config.embedding_model or os.environ.get(
                "EMBEDDING_MODEL", "text-embedding-3-small"
            )
            self._embedder = Embedder(model=model)
        return self._embedder

    def _get_qdrant(self) -> Any:
        """Lazy-init the async Qdrant client."""
        if self._qdrant is None:
            from src.providers.qdrant import get_qdrant_client
            self._qdrant = get_qdrant_client()
        return self._qdrant

    # ── KnowledgeProtocol: build_context ──────────────────────────────────

    def build_context(self, **kwargs: Any) -> str:
        return (
            "You have access to a company knowledge base containing Confluence pages, "
            "Jira tickets, and internal documents. Use the search_knowledge_base tool "
            "to find relevant information before answering. Always cite your sources."
        )

    # ── KnowledgeProtocol: get_tools / aget_tools ─────────────────────────

    def get_tools(self, **kwargs: Any) -> List[Callable]:
        agent = kwargs.get("agent")

        def search_knowledge_base(
            query: str,
            source_type: str | None = None,
            space_key: str | None = None,
            top_k: int | None = None,
        ) -> str:
            """Search the company knowledge base for relevant documents.

            Args:
                query: The search query describing what information you need.
                source_type: Optional. Filter by source system — use ``"confluence"``
                    for Confluence pages or ``"jira"`` for Jira tickets. Omit to
                    search across all sources.
                space_key: Optional. Confluence space key (e.g. ``"TECH"``, ``"PRODUCT"``)
                    or Jira project key to narrow the search to a specific space or
                    project.  Only meaningful when ``source_type`` is also set.
                top_k: Optional. Number of results to return (1–10, default 6).
                    Increase when you need more context; decrease for precision.

            Returns:
                Formatted knowledge base results with source references.
            """
            import asyncio

            params = SearchParams(
                source_type=source_type,
                space_key=space_key,
                top_k=min(int(top_k), 10) if top_k is not None else None,
            )

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    docs = pool.submit(
                        asyncio.run,
                        self._async_search(query, agent=agent, search_params=params),
                    ).result()
            else:
                docs = asyncio.run(
                    self._async_search(query, agent=agent, search_params=params)
                )

            if not docs:
                return "No relevant documents found in the knowledge base."

            return self._format_results(docs)

        return [search_knowledge_base]

    async def aget_tools(self, **kwargs: Any) -> List[Callable]:
        agent = kwargs.get("agent")

        async def search_knowledge_base(
            query: str,
            source_type: str | None = None,
            space_key: str | None = None,
            top_k: int | None = None,
        ) -> str:
            """Search the company knowledge base for relevant documents.

            Args:
                query: The search query describing what information you need.
                source_type: Optional. Filter by source system — use ``"confluence"``
                    for Confluence pages or ``"jira"`` for Jira tickets. Omit to
                    search across all sources.
                space_key: Optional. Confluence space key (e.g. ``"TECH"``, ``"PRODUCT"``)
                    or Jira project key to narrow the search to a specific space or
                    project.  Only meaningful when ``source_type`` is also set.
                top_k: Optional. Number of results to return (1–10, default 6).
                    Increase when you need more context; decrease for precision.

            Returns:
                Formatted knowledge base results with source references.
            """
            params = SearchParams(
                source_type=source_type,
                space_key=space_key,
                top_k=min(int(top_k), 10) if top_k is not None else None,
            )
            docs = await self._async_search(query, agent=agent, search_params=params)
            if not docs:
                return "No relevant documents found in the knowledge base."
            return self._format_results(docs)

        return [search_knowledge_base]

    # ── KnowledgeProtocol: retrieve / aretrieve ───────────────────────────

    def retrieve(self, query: str, **kwargs: Any) -> List[Document]:
        import asyncio

        return asyncio.run(self.aretrieve(query, **kwargs))

    async def aretrieve(self, query: str, **kwargs: Any) -> List[Document]:
        agent = kwargs.get("agent")
        run_context = kwargs.get("run_context")
        return await self._async_search(query, agent=agent, run_context=run_context)

    # ── Internal pipeline ─────────────────────────────────────────────────

    async def _async_search(
        self,
        query: str,
        *,
        agent: Any | None = None,
        search_params: SearchParams | None = None,
        run_context: Any | None = None,
    ) -> List[Document]:
        """Full advanced retrieval pipeline: search → postprocess → citations."""
        cfg = self.config
        log.debug("[VK] _async_search start  query=%r  collection=%s", query, cfg.collection_name)

        # ── Step 0: async Qdrant search ──────────────────────────────────
        try:
            qdrant = self._get_qdrant()
            embedder = self._get_embedder()
        except Exception as exc:
            log.warning("Cannot initialise Qdrant/Embedder: %s — returning empty", exc)
            return []

        query_vector = await embedder.embed(query)
        log.debug("[VK] embedding dim=%d  first-3=%s", len(query_vector), query_vector[:3])

        # 1. Build Qdrant filter from search params + retrieval context
        query_filter = (
            build_search_params_filter(search_params) if search_params else None
        )

        # 2. Async Qdrant search → raw ScoredPoints
        try:
            search_kwargs: dict[str, Any] = dict(
                collection_name=cfg.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=cfg.candidate_limit,
                with_payload=True,
            )
            if cfg.dense_vector_name:
                search_kwargs["using"] = cfg.dense_vector_name
            response = await qdrant.query_points(**search_kwargs)
            raw_points = list(response.points)
        except Exception as exc:
            log.error("Qdrant search failed: %s", exc)
            return []

        log.debug("[VK] Qdrant returned %d raw points", len(raw_points))
        if not raw_points:
            return []

        # 3. Deduplicate raw hits by doc_id (cap per doc)
        deduped_points = deduplicate_hits_by_doc(
            raw_points, max_per_doc=cfg.max_hits_per_doc
        )
        log.debug("[VK] after dedup_by_doc: %d points", len(deduped_points))

        # 4. Convert to RetrievedDocument
        docs: list[RetrievedDocument] = [
            scored_point_to_document(p) for p in deduped_points
        ]
        log.debug("[VK] converted to %d RetrievedDocuments", len(docs))

        # 5. Clean (drop empty/short/junk)
        docs = clean(docs)
        log.debug("[VK] after clean: %d docs", len(docs))
        if not docs:
            return []

        # 6. Content dedup (Jaccard)
        docs = deduplicate_by_content(docs, threshold=cfg.content_dedup_threshold)
        log.debug("[VK] after content dedup: %d docs", len(docs))

        # 7. Group by source (doc_id + section_id)
        groups = group_by_source(docs, max_groups=cfg.max_groups)
        log.debug("[VK] after group_by_source: %d groups", len(groups))

        # 8. Expand groups (async Qdrant scroll: parents/siblings/neighbors)
        blocks = await expand_groups(
            groups,
            cfg.collection_name,
            policy=cfg.expansion_policy,
            max_blocks=cfg.max_blocks,
        )
        log.debug("[VK] after expand_groups: %d blocks", len(blocks))

        # 9. Rerank blocks (CrossEncoder)
        effective_top_n = (
            (search_params.top_k or cfg.rerank_top_n)
            if search_params
            else cfg.rerank_top_n
        )
        blocks = rerank_blocks(query, blocks, top_n=effective_top_n)
        log.debug("[VK] after rerank: %d blocks", len(blocks))

        # 10. Pack blocks (budget-aware)
        effective_max_blocks = (
            (search_params.top_k or cfg.max_pack_blocks)
            if search_params
            else cfg.max_pack_blocks
        )
        packed_refs = pack_blocks(
            blocks,
            max_blocks=effective_max_blocks,
            max_total_chars=cfg.max_total_chars,
            max_block_chars=cfg.max_block_chars,
        )
        log.debug("[VK] after pack_blocks: %d refs", len(packed_refs))

        # 11. Accumulate citations into session_state
        # Write to self.session_state (primary) and run_context.session_state (per-request)
        # so the post-hook can read from whichever is available.
        block_docs = blocks_to_documents(blocks)
        state = self.session_state
        if state is None and agent and hasattr(agent, "session_state"):
            state = agent.session_state
        if state is not None:
            accumulate_citations(block_docs, state)
        # Also write to run_context.session_state for proper per-request scoping.
        if run_context is not None:
            rc_state = getattr(run_context, "session_state", None)
            if rc_state is not None and rc_state is not state:
                accumulate_citations(block_docs, rc_state)

        # 12. Convert packed refs to Agno Documents
        result = self._refs_to_documents(packed_refs)
        log.debug("[VK] final documents: %d", len(result))
        return result

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _refs_to_documents(refs: list[dict[str, Any]]) -> List[Document]:
        """Convert packed reference dicts to Agno Document objects."""
        documents: List[Document] = []
        for ref in refs:
            documents.append(
                Document(
                    content=ref.get("content", ""),
                    name=ref.get("title", ""),
                    meta_data={
                        k: v
                        for k, v in ref.items()
                        if k not in ("content",) and v is not None
                    },
                )
            )
        return documents

    @staticmethod
    def _format_results(docs: List[Document]) -> str:
        """Format documents for LLM consumption."""
        if not docs:
            return "No results found."

        parts: list[str] = []
        for i, doc in enumerate(docs, 1):
            meta = doc.meta_data or {}
            header_parts = [f"[{i}]"]
            if doc.name:
                header_parts.append(doc.name)
            if meta.get("url"):
                header_parts.append(f"({meta['url']})")

            parts.append(" ".join(header_parts))
            parts.append(doc.content)
            parts.append("")  # blank line separator

        return "\n".join(parts).strip()
