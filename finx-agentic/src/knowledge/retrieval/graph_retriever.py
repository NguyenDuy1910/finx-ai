from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.knowledge.graph.models import NodeData
from src.knowledge.graph.store import GraphStore

logger = logging.getLogger(__name__)


@dataclass
class SubGraph:
    seed_nodes: list[NodeData] = field(default_factory=list)
    neighbors: list[dict[str, Any]] = field(default_factory=list)


class GraphRetriever:
    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def search(self, query: str, *, top_k: int = 10) -> list[NodeData]:
        return self._store.search_combined(query, limit=top_k)

    def search_by_domain(self, query: str, domain: str, *, top_k: int = 10) -> list[NodeData]:
        base = self.search(query, top_k=top_k * 2)
        domain_lower = domain.lower()
        filtered = [n for n in base if (n.domain or "").lower() == domain_lower]
        if filtered:
            return filtered[:top_k]
        return base[:top_k]

    def search_with_column_hints(
        self,
        query: str,
        column_names: list[str],
        *,
        top_k: int = 10,
    ) -> SubGraph:
        seeds = self.search(query, top_k=top_k)
        if column_names:
            col_upper = {c.upper() for c in column_names}
            boosted = [n for n in seeds if n.node_id in col_upper]
            rest = [n for n in seeds if n.node_id not in col_upper]
            seeds = (boosted + rest)[:top_k]
        return self.expand(seeds)

    def expand(self, seeds: list[NodeData], *, depth: int = 1, limit: int = 50) -> SubGraph:
        seed_names = [n.node_id for n in seeds]
        neighbors = self._store.neighborhood_expand(seed_names, depth=depth, limit=limit)
        return SubGraph(seed_nodes=seeds, neighbors=neighbors)

    def search_and_expand(
        self,
        query: str,
        *,
        top_k: int = 10,
        expand_limit: int = 50,
    ) -> SubGraph:
        seeds = self.search(query, top_k=top_k)
        return self.expand(seeds, limit=expand_limit)

    @staticmethod
    def format_context(subgraph: SubGraph) -> str:
        parts: list[str] = []

        for node in subgraph.seed_nodes:
            lines = [f"[{node.label}] {node.name}"]
            if node.description:
                lines.append(f"  {node.description}")
            if node.domain:
                lines.append(f"  Domain: {node.domain}")
            if node.synonyms:
                lines.append(f"  Synonyms: {', '.join(node.synonyms)}")
            for key, val in node.extra.items():
                if val:
                    lines.append(f"  {key}: {val}")
            parts.append("\n".join(lines))

        if subgraph.neighbors:
            edge_lines: list[str] = []
            for nb in subgraph.neighbors:
                tgt_props = nb.get("tgt_props", {})
                tgt_label = tgt_props.get("label", "")
                tgt_desc = tgt_props.get("description", "")
                line = f"  -> {nb['edge_type']} -> [{tgt_label}] {nb['tgt']}"
                if tgt_desc:
                    line += f" ({tgt_desc[:100]})"
                edge_lines.append(line)
            if edge_lines:
                parts.append("Relationships:\n" + "\n".join(edge_lines))

        return "\n\n".join(parts) if parts else "No relevant knowledge found."
