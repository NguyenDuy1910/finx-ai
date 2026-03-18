from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, List

from agno.knowledge.document.base import Document

from .reranker import DocumentReranker

log = logging.getLogger("finx-agentic.qdrant-knowledge")


class QdrantKnowledge:
    """Qdrant-backed knowledge base for Confluence document retrieval.

    Satisfies Agno's KnowledgeProtocol so it can be passed directly to
    ``Agent(knowledge=...)``.

    Args:
        qdrant_url: Qdrant server URL.
        collection_name: Name of the Qdrant collection to search.
        embedding_model: OpenAI embedding model (must match ingestion model).
        reranker: DocumentReranker instance.
        top_k: Number of candidates to retrieve before reranking.
        rerank_top_n: Final number of documents after reranking.
        min_score: Minimum Qdrant score threshold (0.0 = no filter).
    """

    def __init__(
        self,
        *,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        collection_name: str = "finx_knowledge",
        embedding_model: str = "text-embedding-3-small",
        reranker: DocumentReranker | None = None,
        top_k: int = 20,
        rerank_top_n: int = 5,
        min_score: float = 0.0,
    ) -> None:
        self._url = qdrant_url or os.environ.get("QDRANT_URL", "http://localhost:6333")
        self._api_key = qdrant_api_key or os.environ.get("QDRANT_API_KEY")
        self._collection = collection_name
        self._embedding_model = embedding_model
        self._reranker = reranker or DocumentReranker()
        self._top_k = top_k
        self._rerank_top_n = rerank_top_n
        self._min_score = min_score
        self._client: Any = None  # AsyncQdrantClient, lazy-init
        self._openai: Any = None  # openai.AsyncOpenAI, lazy-init

    # ── Lazy client setup ─────────────────────────────────────────────────

    def _get_client(self) -> Any:
        if self._client is None:
            from qdrant_client import AsyncQdrantClient

            self._client = AsyncQdrantClient(url=self._url, api_key=self._api_key)
        return self._client

    def _get_openai(self) -> Any:
        if self._openai is None:
            from openai import AsyncOpenAI

            self._openai = AsyncOpenAI()
        return self._openai

    # ── KnowledgeProtocol ─────────────────────────────────────────────────

    def build_context(self, **kwargs: Any) -> str:
        return (
            "You have access to company knowledge from internal Confluence documents. "
            "Use the knowledge search to find answers about company policies, "
            "procedures, technical specifications, business rules, and project documentation."
        )

    def get_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    async def aget_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    def retrieve(self, query: str, **kwargs: Any) -> List[Document]:
        """Sync wrapper around aretrieve."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.aretrieve(query, **kwargs)).result()
        return asyncio.run(self.aretrieve(query, **kwargs))

    async def aretrieve(self, query: str, **kwargs: Any) -> List[Document]:
        """Embed query → search Qdrant → rerank → return top documents."""
        top_k: int = kwargs.get("top_k", self._top_k)
        rerank_top_n: int = kwargs.get("rerank_top_n", self._rerank_top_n)

        # Optional Qdrant payload filters passed from agent session_state
        qdrant_filter = _build_filter(kwargs)

        # 1. Embed query
        try:
            vector = await self._embed(query)
        except Exception as exc:
            log.error("Failed to embed query '%s': %s", query[:60], exc)
            return []

        # 2. Search Qdrant
        try:
            client = self._get_client()
            results = await client.query_points(
                collection_name=self._collection,
                query=vector,
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
                score_threshold=self._min_score if self._min_score > 0 else None,
            )
            hits = results.points
        except Exception as exc:
            log.error("Qdrant search failed: %s", exc)
            return []

        if not hits:
            log.debug("QdrantKnowledge: no hits for query=%r", query[:60])
            return []

        # 3. Convert to Agno Documents
        docs = [_hit_to_document(hit) for hit in hits]
        log.debug("QdrantKnowledge: retrieved %d docs from Qdrant", len(docs))

        # 4. Rerank
        reranked = self._reranker.rerank(query, docs, top_n=rerank_top_n)
        log.debug("QdrantKnowledge: reranked to %d docs", len(reranked))

        return reranked

    # ── Internal tool exposed to the Agno agent ───────────────────────────

    async def _search_tool(self, query: str) -> str:
        """Search the company knowledge base for relevant documents.

        Use this when the user asks about company policies, procedures,
        technical specifications, business rules, or project documentation.
        Returns document summaries with page IDs so you can fetch full content
        via confluence_get_page when the summary is insufficient.
        """
        docs = await self.aretrieve(query)
        if not docs:
            return "No relevant company knowledge found for this query."

        parts: list[str] = []
        for i, doc in enumerate(docs, 1):
            meta = doc.meta_data or {}
            source = meta.get("source_uri", "")
            title = meta.get("title", f"Document {i}")
            doc_id = meta.get("source_document_id", "")
            score = meta.get("rerank_score", "")
            score_str = f" (relevance: {score:.3f})" if isinstance(score, float) else ""

            header = f"[{i}] {title}{score_str}"
            if source:
                header += f"\nSource: {source}"
            if doc_id:
                header += f"\nPage ID: {doc_id}  ← use with confluence_get_page to fetch full content"
            parts.append(f"{header}\n{doc.content or ''}")

        return "\n\n---\n\n".join(parts)

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _embed(self, text: str) -> list[float]:
        """Embed text using the same model as ingestion."""
        client = self._get_openai()
        response = await client.embeddings.create(
            input=[text],
            model=self._embedding_model,
        )
        return response.data[0].embedding


# ── Qdrant result → Agno Document ────────────────────────────────────────────

def _hit_to_document(hit: Any) -> Document:
    """Convert a Qdrant ScoredPoint to an Agno Document."""
    payload: dict = hit.payload or {}

    title = payload.get("title", "")
    summary = payload.get("summary", "")
    source_uri = payload.get("source_uri", "")
    document_type = payload.get("document_type", "")
    domains: list[str] = payload.get("domains", [])
    language = payload.get("language", "")
    key_entities: list[str] = payload.get("key_entities", [])
    space_key = payload.get("space_key", "")
    source_document_id = payload.get("source_document_id", "")

    # Structured content fields (richer detail than summary alone)
    salient_points: list[str] = payload.get("salient_points", [])
    definitions: list[dict] = payload.get("definitions", [])
    key_concepts: list[str] = payload.get("key_concepts", [])
    insights: list[str] = payload.get("insights", [])

    # Build readable content block for the agent
    content_parts: list[str] = []
    if title:
        content_parts.append(f"Title: {title}")
    if document_type:
        content_parts.append(f"Type: {document_type}")
    if domains:
        content_parts.append(f"Domains: {', '.join(domains)}")
    if language:
        content_parts.append(f"Language: {language}")
    if summary:
        content_parts.append(f"\nSummary:\n{summary}")
    if salient_points:
        content_parts.append("\nKey points:\n" + "\n".join(f"- {p}" for p in salient_points[:10]))
    if definitions:
        defs_str = "\n".join(
            f"- {d.get('term', '')}: {d.get('definition', '')}"
            for d in definitions[:8]
            if d.get("term")
        )
        if defs_str:
            content_parts.append(f"\nDefinitions:\n{defs_str}")
    if key_concepts:
        content_parts.append(f"\nKey concepts: {', '.join(key_concepts[:10])}")
    if insights:
        content_parts.append("\nInsights:\n" + "\n".join(f"- {ins}" for ins in insights[:5]))
    if key_entities:
        content_parts.append(f"\nEntities: {', '.join(key_entities[:15])}")
    if source_uri:
        content_parts.append(f"\nSource: {source_uri}")
    if source_document_id:
        content_parts.append(f"Page ID: {source_document_id}")

    content = "\n".join(content_parts)

    return Document(
        name=title or source_document_id or str(hit.id),
        content=content,
        meta_data={
            "title": title,
            "source_uri": source_uri,
            "source_document_id": source_document_id,
            "document_type": document_type,
            "domains": domains,
            "language": language,
            "space_key": space_key,
            "qdrant_score": float(hit.score),
            "point_id": str(hit.id),
        },
    )


def _build_filter(kwargs: dict) -> Any | None:
    """Build a Qdrant Filter from optional keyword arguments.

    Supported kwargs:
        language (str): filter by exact language code
        domain (str): filter by domain value in array
        document_type (str): filter by document_type
        min_quality (float): filter by quality_score >= value
    """
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        conditions: list[Any] = []

        if language := kwargs.get("language"):
            conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))

        if domain := kwargs.get("domain"):
            conditions.append(FieldCondition(key="domains", match=MatchValue(value=domain)))

        if doc_type := kwargs.get("document_type"):
            conditions.append(FieldCondition(key="document_type", match=MatchValue(value=doc_type)))

        if min_quality := kwargs.get("min_quality"):
            conditions.append(FieldCondition(key="quality_score", range=Range(gte=float(min_quality))))

        return Filter(must=conditions) if conditions else None

    except Exception:
        return None
