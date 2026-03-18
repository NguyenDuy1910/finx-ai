"""GraphKnowledgeV2 — Graphiti-backed knowledge that satisfies Agno's KnowledgeProtocol.

Uses Graphiti's native hybrid search (embedding + BM25 + graph neighbourhood)
and presents results as Agno ``Document`` objects so agents can call
``search_knowledge`` or rely on ``add_knowledge_to_context``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Callable, List

from agno.knowledge.document.base import Document
from agno.knowledge.protocol import KnowledgeProtocol

if TYPE_CHECKING:
    from src.core.graph.client import GraphitiClient

logger = logging.getLogger(__name__)


class GraphKnowledgeV2:
    """Graphiti-backed knowledge base satisfying ``KnowledgeProtocol``.

    Designed to be passed directly to an Agno ``Agent`` as ``knowledge=``.
    All retrieval goes through ``GraphitiClient.search_nodes_and_edges()``.

    Args:
        client: Shared ``GraphitiClient`` singleton.
        max_results: Default number of results per query.
    """

    def __init__(self, client: "GraphitiClient", *, max_results: int = 5) -> None:
        self._client = client
        self._max_results = max_results

    # ── KnowledgeProtocol ─────────────────────────────────────────────────

    def build_context(self, **kwargs: Any) -> str:
        return (
            "You have access to a Graphiti knowledge graph containing schema metadata, "
            "business rules, and relationships. Use `search_knowledge` to look up "
            "table/column details, metrics, or domain concepts before writing SQL."
        )

    def get_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    async def aget_tools(self, **kwargs: Any) -> List[Callable]:
        return [self._search_tool]

    def retrieve(self, query: str, **kwargs: Any) -> List[Document]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        n: int = kwargs.get("max_results", self._max_results)
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.aretrieve(query, max_results=n)).result()
        return asyncio.run(self.aretrieve(query, max_results=n))

    async def aretrieve(self, query: str, **kwargs: Any) -> List[Document]:
        """Retrieve knowledge from the graph using Graphiti hybrid search."""
        max_results: int = kwargs.get("max_results", self._max_results)
        try:
            results = await self._client.search_nodes_and_edges(
                query=query,
                num_results=max_results,
            )
        except Exception as exc:
            logger.warning("GraphKnowledgeV2.aretrieve: search failed: %s", exc)
            return []

        documents: list[Document] = []

        for node in getattr(results, "nodes", []):
            name = getattr(node, "name", None) or str(getattr(node, "uuid", "unknown"))
            labels = list(getattr(node, "labels", []))
            summary = getattr(node, "summary", "") or ""
            attributes = getattr(node, "attributes", {}) or {}

            documents.append(Document(
                content=_format_node(name, labels, summary, attributes),
                name=name,
                meta_data={
                    "type": _classify_node(labels),
                    "labels": labels,
                    "uuid": str(getattr(node, "uuid", "")),
                    "score": float(getattr(node, "score", 0.0) or 0.0),
                },
            ))

        for edge in getattr(results, "edges", []):
            fact = getattr(edge, "fact", "") or ""
            if not fact.strip():
                continue
            name = getattr(edge, "name", None) or str(getattr(edge, "uuid", "edge"))
            documents.append(Document(
                content=fact,
                name=name,
                meta_data={
                    "type": "relationship",
                    "uuid": str(getattr(edge, "uuid", "")),
                    "source_node": str(getattr(edge, "source_node_uuid", "")),
                    "target_node": str(getattr(edge, "target_node_uuid", "")),
                    "episode_count": len(getattr(edge, "episodes", []) or []),
                    "score": float(getattr(edge, "score", 0.0) or 0.0),
                },
            ))

        logger.debug(
            "GraphKnowledgeV2.aretrieve: query=%r → %d nodes, %d edges → %d documents",
            query[:60],
            len(getattr(results, "nodes", [])),
            len(getattr(results, "edges", [])),
            len(documents),
        )
        return documents

    # ── Internal tool exposed to agents ───────────────────────────────────

    async def _search_tool(self, query: str) -> str:
        """Search the knowledge graph for schema metadata, metrics, or business rules."""
        docs = await self.aretrieve(query)
        if not docs:
            return "No relevant knowledge found."
        return "\n\n".join(d.content for d in docs if d.content)


# Verify protocol compliance at import time (no-op at runtime, catches drift early)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _format_node(
    name: str,
    labels: list[str],
    summary: str,
    attributes: dict[str, Any],
) -> str:
    parts: list[str] = [f"name: {name}"]
    if labels:
        parts.append(f"type: {', '.join(labels)}")
    if summary:
        parts.append(f"summary: {summary}")
    for key in (
        "data_type", "domain", "description", "table_name", "database",
        "is_primary_key", "sample_values", "unit", "aggregation_method",
        "certification_status", "join_condition",
    ):
        val = attributes.get(key)
        if val is not None and val != "" and val != []:
            parts.append(f"{key}: {json.dumps(val) if isinstance(val, (list, dict)) else val}")
    return "\n".join(parts)


_NODE_TYPE_MAP: dict[str, str] = {
    "Table": "table_context",
    "Column": "column",
    "Metric": "entity",
    "BusinessTerm": "entity",
    "Dimension": "entity",
    "JoinPath": "join_path",
    "SQLPattern": "query_pattern",
    "QueryIntent": "query_pattern",
    "ExampleQuestion": "query_pattern",
}


def _classify_node(labels: list[str]) -> str:
    for label in labels:
        if label in _NODE_TYPE_MAP:
            return _NODE_TYPE_MAP[label]
    return "entity"
