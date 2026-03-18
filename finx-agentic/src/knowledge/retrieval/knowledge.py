"""Agno KnowledgeProtocol adapter wrapping GraphRetriever.

Drop-in replacement for the old ``GraphKnowledgeV2`` that used Graphiti.
Agents use this via ``knowledge=GraphKnowledge(...)`` in their config.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable, List

from agno.knowledge.document.base import Document
from agno.knowledge.protocol import KnowledgeProtocol

from .graph_retriever import GraphRetriever

if TYPE_CHECKING:
    from src.knowledge.graph.store import GraphStore

logger = logging.getLogger(__name__)


class GraphKnowledge:
    """Graph-backed knowledge base satisfying ``KnowledgeProtocol``.

    Designed to be passed directly to an Agno ``Agent`` as ``knowledge=``.

    Args:
        store: ``GraphStore`` instance.
        max_results: Default number of results per query.
    """

    def __init__(self, store: "GraphStore", *, max_results: int = 10) -> None:
        self._retriever = GraphRetriever(store)
        self._max_results = max_results

    # ── KnowledgeProtocol ─────────────────────────────────────────────────

    def build_context(self, **kwargs: Any) -> str:
        return (
            "You have access to a knowledge graph containing banking schema metadata, "
            "business terms, metrics, and relationships. Use `search_knowledge` to look up "
            "table/column details, metrics, or domain concepts before writing SQL."
        )

    def get_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    async def aget_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    def retrieve(self, query: str, **kwargs: Any) -> List[Document]:
        """Synchronous retrieval."""
        n: int = kwargs.get("max_results", self._max_results)
        subgraph = self._retriever.search_and_expand(query, top_k=n)
        return self._subgraph_to_documents(subgraph)

    async def aretrieve(self, query: str, **kwargs: Any) -> List[Document]:
        """Async retrieval (delegates to sync — FalkorDB driver is sync)."""
        return self.retrieve(query, **kwargs)

    # ── internal ───────────────────────────────────────────────────────────

    def _subgraph_to_documents(self, subgraph: Any) -> List[Document]:
        documents: List[Document] = []

        for node in subgraph.seed_nodes:
            content_parts = [f"[{node.label}] {node.name}"]
            if node.description:
                content_parts.append(node.description)
            if node.domain:
                content_parts.append(f"Domain: {node.domain}")
            if node.synonyms:
                content_parts.append(f"Synonyms: {', '.join(node.synonyms)}")
            for key, val in node.extra.items():
                if val:
                    content_parts.append(f"{key}: {val}")

            documents.append(Document(
                content="\n".join(content_parts),
                name=node.name,
                meta_data={
                    "type": node.label.lower(),
                    "domain": node.domain,
                    "node_id": node.node_id,
                },
            ))

        # Add neighbor nodes as documents too (compact)
        seen: set[str] = {n.node_id for n in subgraph.seed_nodes}
        for nb in subgraph.neighbors:
            tgt_name = nb.get("tgt", "")
            if tgt_name.upper() in seen:
                continue
            seen.add(tgt_name.upper())

            tgt_props = nb.get("tgt_props", {})
            content = f"[{tgt_props.get('label', '')}] {tgt_name}"
            desc = tgt_props.get("description", "")
            if desc:
                content += f"\n{desc}"

            documents.append(Document(
                content=content,
                name=tgt_name,
                meta_data={
                    "type": "neighbor",
                    "edge_type": nb.get("edge_type", ""),
                    "from": nb.get("src", ""),
                },
            ))

        logger.debug(
            "GraphKnowledge.retrieve: %d seed + %d neighbor → %d documents",
            len(subgraph.seed_nodes),
            len(subgraph.neighbors),
            len(documents),
        )
        return documents

    async def _search_tool(self, query: str) -> str:
        """Tool exposed to agents for knowledge search."""
        docs = self.retrieve(query)
        if not docs:
            return "No relevant knowledge found."
        return "\n\n".join(d.content for d in docs if d.content)
