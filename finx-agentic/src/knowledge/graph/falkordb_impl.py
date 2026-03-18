from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from config.config_loader import AppConfig

from .base import BaseKVStorage
from .client import FalkorDBClient

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeGraphNode:
    id: str
    labels: list[str]
    properties: dict[str, Any]


@dataclass
class KnowledgeGraphEdge:
    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any]


@dataclass
class KnowledgeGraph:
    nodes: list[KnowledgeGraphNode] = field(default_factory=list)
    edges: list[KnowledgeGraphEdge] = field(default_factory=list)
    is_truncated: bool = False


class FalkorDbImpl(BaseKVStorage):

    def __init__(
        self,
        namespace: str,
        global_config: AppConfig,
        embedding_func: Any,
        workspace: str | None = None,
    ) -> None:
        falkordb_workspace = os.environ.get("FALKORDB_WORKSPACE")
        if falkordb_workspace and falkordb_workspace.strip():
            workspace = falkordb_workspace
        if not workspace or not str(workspace).strip():
            workspace = "base"

        self.namespace = namespace
        self.global_config = global_config
        self._embedding_func = embedding_func
        self.workspace = workspace

        cfg = global_config.falkordb
        self._client = FalkorDBClient(
            host=cfg.host,
            port=cfg.port,
            graph_name=namespace,
        )

    def _ws(self) -> str:
        return self.workspace

    def _run(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return self._client.execute(query, params)

    async def _arun(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return await asyncio.to_thread(self._run, query, params)

    async def initialize(self) -> None:
        ws = self._ws()
        try:
            await self._arun(f"CREATE INDEX FOR (n:`{ws}`) ON (n.entity_id)")
        except Exception as e:
            logger.warning("B-tree index creation: %s", e)
        try:
            await self._arun(
                f"CALL db.idx.fulltext.createNodeIndex('{ws}', 'entity_id')"
            )
        except Exception as e:
            logger.warning("Fulltext index creation: %s", e)

    async def finalize(self) -> None:
        await asyncio.to_thread(self._client.close)

    async def index_done_callback(self) -> None:
        pass

    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        return await self.get_node(id)

    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        batch = await self.get_nodes_batch(ids)
        return [batch[i] for i in ids if i in batch]

    async def filter_keys(self, keys: set[str]) -> set[str]:
        if not keys:
            return set()
        key_list = list(keys)
        result = await self._arun(
            f"MATCH (n:`{self._ws()}`) WHERE n.entity_id IN $ids RETURN n.entity_id AS id",
            {"ids": key_list},
        )
        found = {row[0] for row in (result.result_set or [])}
        return {k for k in keys if k not in found}

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        for node_id, props in data.items():
            node_data = dict(props)
            node_data.setdefault("entity_id", node_id)
            await self.upsert_node(node_id, node_data)

    async def delete(self, ids: list[str]) -> None:
        for id_ in ids:
            await self.delete_node(id_)

    async def is_empty(self) -> bool:
        result = await self._arun(
            f"MATCH (n:`{self._ws()}`) RETURN count(n) AS c LIMIT 1"
        )
        return not result.result_set or result.result_set[0][0] == 0

    async def has_node(self, node_id: str) -> bool:
        result = await self._arun(
            f"MATCH (n:`{self._ws()}` {{entity_id: $id}}) RETURN count(n) > 0 AS c",
            {"id": node_id},
        )
        return bool(result.result_set and result.result_set[0][0])

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (n:`{ws}` {{entity_id: $id}}) RETURN properties(n) AS props",
            {"id": node_id},
        )
        if not result.result_set:
            return None
        rows = result.result_set
        if len(rows) > 1:
            logger.warning("Multiple nodes found for entity_id '%s', using first", node_id)
        return dict(rows[0][0])

    async def get_nodes_batch(self, node_ids: list[str]) -> dict[str, dict[str, Any]]:
        ws = self._ws()
        result = await self._arun(
            f"UNWIND $ids AS id "
            f"MATCH (n:`{ws}` {{entity_id: id}}) "
            f"RETURN n.entity_id AS entity_id, properties(n) AS props",
            {"ids": node_ids},
        )
        return {row[0]: dict(row[1]) for row in (result.result_set or [])}

    async def upsert_node(self, node_id: str, node_data: dict[str, Any]) -> None:
        ws = self._ws()
        props = dict(node_data)
        props["entity_id"] = node_id
        entity_type = props.get("entity_type", "UNKNOWN")
        if not isinstance(entity_type, str):
            entity_type = str(entity_type)
        entity_type = entity_type.replace("`", "").strip()
        if "," in entity_type:
            entity_type = entity_type.split(",")[0].strip()
        if not entity_type:
            entity_type = "UNKNOWN"
        props["entity_type"] = entity_type
        await self._arun(
            f"MERGE (n:`{ws}` {{entity_id: $id}}) "
            f"SET n += $props "
            f"SET n:`{entity_type}`",
            {"id": node_id, "props": props},
        )

    async def delete_node(self, node_id: str) -> None:
        ws = self._ws()
        await self._arun(
            f"MATCH (n:`{ws}` {{entity_id: $id}}) DETACH DELETE n",
            {"id": node_id},
        )

    async def remove_nodes(self, nodes: list[str]) -> None:
        for node in nodes:
            await self.delete_node(node)

    async def get_all_nodes(self) -> list[dict[str, Any]]:
        ws = self._ws()
        result = await self._arun(f"MATCH (n:`{ws}`) RETURN properties(n) AS props")
        nodes = []
        for row in (result.result_set or []):
            d = dict(row[0])
            d["id"] = d.get("entity_id")
            nodes.append(d)
        return nodes

    async def get_all_labels(self) -> list[str]:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (n:`{ws}`) WHERE n.entity_id IS NOT NULL "
            f"RETURN DISTINCT n.entity_id AS label ORDER BY label"
        )
        return [row[0] for row in (result.result_set or [])]

    async def get_popular_labels(self, limit: int = 300) -> list[str]:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (n:`{ws}`) WHERE n.entity_id IS NOT NULL "
            f"OPTIONAL MATCH (n)-[r]-() "
            f"WITH n.entity_id AS label, count(r) AS degree "
            f"ORDER BY degree DESC, label ASC "
            f"LIMIT $limit "
            f"RETURN label",
            {"limit": limit},
        )
        return [row[0] for row in (result.result_set or [])]

    async def search_labels(self, query: str, limit: int = 50) -> list[str]:
        ws = self._ws()
        query_strip = query.strip()
        if not query_strip:
            return []
        query_lower = query_strip.lower()
        try:
            result = await self._arun(
                f"CALL db.idx.fulltext.queryNodes('{ws}', $q) YIELD node "
                f"WHERE node.entity_id IS NOT NULL "
                f"RETURN node.entity_id AS label "
                f"LIMIT $limit",
                {"q": query_strip, "limit": limit},
            )
            labels = [row[0] for row in (result.result_set or [])]
            if labels:
                return labels
        except Exception as e:
            logger.warning("Fulltext search failed: %s", e)
        result = await self._arun(
            f"MATCH (n:`{ws}`) "
            f"WHERE n.entity_id IS NOT NULL AND toLower(n.entity_id) CONTAINS $q "
            f"WITH n.entity_id AS label, toLower(n.entity_id) AS label_lower "
            f"WITH label, label_lower, "
            f"CASE WHEN label_lower = $q THEN 1000 "
            f"     WHEN label_lower STARTS WITH $q THEN 500 "
            f"     ELSE 100 - size(label) END AS score "
            f"ORDER BY score DESC, label ASC "
            f"LIMIT $limit "
            f"RETURN label",
            {"q": query_lower, "limit": limit},
        )
        return [row[0] for row in (result.result_set or [])]

    async def node_degree(self, node_id: str) -> int:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (n:`{ws}` {{entity_id: $id}}) "
            f"OPTIONAL MATCH (n)-[r]-() "
            f"RETURN count(r) AS degree",
            {"id": node_id},
        )
        if not result.result_set:
            return 0
        return int(result.result_set[0][0] or 0)

    async def node_degrees_batch(self, node_ids: list[str]) -> dict[str, int]:
        ws = self._ws()
        result = await self._arun(
            f"UNWIND $ids AS id "
            f"MATCH (n:`{ws}` {{entity_id: id}}) "
            f"OPTIONAL MATCH (n)-[r]-() "
            f"RETURN n.entity_id AS entity_id, count(r) AS degree",
            {"ids": node_ids},
        )
        degrees = {row[0]: int(row[1] or 0) for row in (result.result_set or [])}
        for nid in node_ids:
            if nid not in degrees:
                degrees[nid] = 0
        return degrees

    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        src = await self.node_degree(src_id)
        tgt = await self.node_degree(tgt_id)
        return src + tgt

    async def edge_degrees_batch(
        self, edge_pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        unique = {src for src, _ in edge_pairs} | {tgt for _, tgt in edge_pairs}
        degrees = await self.node_degrees_batch(list(unique))
        return {(s, t): degrees.get(s, 0) + degrees.get(t, 0) for s, t in edge_pairs}

    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (a:`{ws}` {{entity_id: $src}})-[r]-(b:`{ws}` {{entity_id: $tgt}}) "
            f"RETURN count(r) > 0 AS c",
            {"src": source_node_id, "tgt": target_node_id},
        )
        return bool(result.result_set and result.result_set[0][0])

    async def get_edge(
        self, source_node_id: str, target_node_id: str
    ) -> dict[str, Any] | None:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (a:`{ws}` {{entity_id: $src}})-[r]-(b:`{ws}` {{entity_id: $tgt}}) "
            f"RETURN properties(r) AS props LIMIT 2",
            {"src": source_node_id, "tgt": target_node_id},
        )
        rows = result.result_set or []
        if not rows:
            return None
        if len(rows) > 1:
            logger.warning(
                "Multiple edges between '%s' and '%s', using first",
                source_node_id,
                target_node_id,
            )
        props = dict(rows[0][0])
        for k, v in {"weight": 1.0, "source_id": None, "description": None, "keywords": None}.items():
            props.setdefault(k, v)
        return props

    async def get_edges_batch(
        self, pairs: list[dict[str, str]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        ws = self._ws()
        result = await self._arun(
            f"UNWIND $pairs AS pair "
            f"MATCH (a:`{ws}` {{entity_id: pair.src}})-[r:DIRECTED]-(b:`{ws}` {{entity_id: pair.tgt}}) "
            f"RETURN pair.src AS src, pair.tgt AS tgt, collect(properties(r)) AS edges",
            {"pairs": pairs},
        )
        out: dict[tuple[str, str], dict[str, Any]] = {}
        defaults = {"weight": 1.0, "source_id": None, "description": None, "keywords": None}
        for row in (result.result_set or []):
            src, tgt, edges = row[0], row[1], row[2]
            props = dict(edges[0]) if edges else {}
            for k, v in defaults.items():
                props.setdefault(k, v)
            out[(src, tgt)] = props
        return out

    async def get_node_edges(
        self, source_node_id: str
    ) -> list[tuple[str, str]] | None:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (n:`{ws}` {{entity_id: $id}}) "
            f"OPTIONAL MATCH (n)-[r]-(m:`{ws}`) "
            f"WHERE m.entity_id IS NOT NULL "
            f"RETURN n.entity_id AS src, m.entity_id AS tgt",
            {"id": source_node_id},
        )
        edges = []
        for row in (result.result_set or []):
            src, tgt = row[0], row[1]
            if src and tgt:
                edges.append((src, tgt))
        return edges

    async def get_nodes_edges_batch(
        self, node_ids: list[str]
    ) -> dict[str, list[tuple[str, str]]]:
        ws = self._ws()
        result = await self._arun(
            f"UNWIND $ids AS id "
            f"MATCH (n:`{ws}` {{entity_id: id}}) "
            f"OPTIONAL MATCH (n)-[r]-(m:`{ws}`) "
            f"RETURN id AS queried_id, n.entity_id AS node_id, "
            f"m.entity_id AS connected_id, startNode(r).entity_id AS start_id",
            {"ids": node_ids},
        )
        out: dict[str, list[tuple[str, str]]] = {nid: [] for nid in node_ids}
        for row in (result.result_set or []):
            queried_id, node_id, connected_id, start_id = row[0], row[1], row[2], row[3]
            if not node_id or not connected_id:
                continue
            if start_id == node_id:
                out[queried_id].append((node_id, connected_id))
            else:
                out[queried_id].append((connected_id, node_id))
        return out

    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, Any]
    ) -> None:
        ws = self._ws()
        await self._arun(
            f"MATCH (a:`{ws}` {{entity_id: $src}}) "
            f"WITH a "
            f"MATCH (b:`{ws}` {{entity_id: $tgt}}) "
            f"MERGE (a)-[r:DIRECTED]-(b) "
            f"SET r += $props",
            {"src": source_node_id, "tgt": target_node_id, "props": edge_data},
        )

    async def remove_edges(self, edges: list[tuple[str, str]]) -> None:
        ws = self._ws()
        for src, tgt in edges:
            await self._arun(
                f"MATCH (a:`{ws}` {{entity_id: $src}})-[r]-(b:`{ws}` {{entity_id: $tgt}}) "
                f"DELETE r",
                {"src": src, "tgt": tgt},
            )

    async def get_all_edges(self) -> list[dict[str, Any]]:
        ws = self._ws()
        result = await self._arun(
            f"MATCH (a:`{ws}`)-[r]-(b:`{ws}`) "
            f"RETURN DISTINCT a.entity_id AS source, b.entity_id AS target, properties(r) AS props"
        )
        edges = []
        for row in (result.result_set or []):
            props = dict(row[2])
            props["source"] = row[0]
            props["target"] = row[1]
            edges.append(props)
        return edges

    async def get_knowledge_graph(
        self,
        node_label: str,
        max_depth: int = 3,
        max_nodes: int | None = None,
    ) -> KnowledgeGraph:
        if max_nodes is None:
            max_nodes = getattr(self.global_config, "max_graph_nodes", 1000)

        result = KnowledgeGraph()
        ws = self._ws()

        if node_label == "*":
            count_result = await self._arun(
                f"MATCH (n:`{ws}`) RETURN count(n) AS total"
            )
            total = count_result.result_set[0][0] if count_result.result_set else 0
            if total > max_nodes:
                result.is_truncated = True

            nodes_result = await self._arun(
                f"MATCH (n:`{ws}`) "
                f"OPTIONAL MATCH (n)-[r]-() "
                f"WITH n, count(r) AS degree "
                f"ORDER BY degree DESC "
                f"LIMIT $limit "
                f"RETURN n.entity_id AS nid, properties(n) AS props",
                {"limit": max_nodes},
            )
            kept_ids: set[str] = set()
            for row in (nodes_result.result_set or []):
                nid, props = row[0], dict(row[1])
                if nid and nid not in kept_ids:
                    result.nodes.append(
                        KnowledgeGraphNode(id=nid, labels=[nid], properties=props)
                    )
                    kept_ids.add(nid)

            if kept_ids:
                edges_result = await self._arun(
                    f"UNWIND $ids AS id "
                    f"MATCH (a:`{ws}` {{entity_id: id}})-[r]-(b:`{ws}`) "
                    f"WHERE b.entity_id IN $ids "
                    f"RETURN a.entity_id AS src, type(r) AS rtype, b.entity_id AS tgt, "
                    f"id(r) AS rid, properties(r) AS props",
                    {"ids": list(kept_ids)},
                )
                seen_edges: set[str] = set()
                for row in (edges_result.result_set or []):
                    src, rtype, tgt, rid, props = row[0], row[1], row[2], str(row[3]), dict(row[4])
                    if rid not in seen_edges:
                        result.edges.append(
                            KnowledgeGraphEdge(id=rid, type=rtype, source=src, target=tgt, properties=props)
                        )
                        seen_edges.add(rid)
            return result

        start = await self.get_node(node_label)
        if not start:
            return result

        visited_nodes: set[str] = set()
        visited_edges: set[str] = set()
        visited_edge_pairs: set[tuple[str, str]] = set()

        result.nodes.append(
            KnowledgeGraphNode(id=node_label, labels=[node_label], properties=start)
        )
        visited_nodes.add(node_label)

        queue: deque[tuple[str, int]] = deque([(node_label, 0)])

        while queue and len(visited_nodes) < max_nodes:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            neighbors_result = await self._arun(
                f"MATCH (a:`{ws}` {{entity_id: $id}})-[r]-(b:`{ws}`) "
                f"WHERE b.entity_id IS NOT NULL "
                f"RETURN b.entity_id AS nid, properties(b) AS nprops, "
                f"type(r) AS rtype, id(r) AS rid, properties(r) AS rprops, "
                f"startNode(r).entity_id AS start_id",
                {"id": current_id},
            )

            for row in (neighbors_result.result_set or []):
                nid = row[0]
                nprops = dict(row[1])
                rtype = row[2]
                rid = str(row[3])
                rprops = dict(row[4])
                start_id = row[5]

                if not nid:
                    continue

                pair: tuple[str, str] = tuple(sorted([current_id, nid]))  # type: ignore[assignment]
                if pair not in visited_edge_pairs:
                    src_e = current_id if start_id == current_id else nid
                    tgt_e = nid if start_id == current_id else current_id
                    result.edges.append(
                        KnowledgeGraphEdge(id=rid, type=rtype, source=src_e, target=tgt_e, properties=rprops)
                    )
                    visited_edges.add(rid)
                    visited_edge_pairs.add(pair)

                if nid not in visited_nodes:
                    if len(visited_nodes) >= max_nodes:
                        result.is_truncated = True
                        break
                    result.nodes.append(
                        KnowledgeGraphNode(id=nid, labels=[nid], properties=nprops)
                    )
                    visited_nodes.add(nid)
                    queue.append((nid, depth + 1))

        return result

    async def drop(self) -> dict[str, str]:
        ws = self._ws()
        try:
            await self._arun(f"MATCH (n:`{ws}`) DETACH DELETE n")
            return {"status": "success", "message": f"workspace '{ws}' data dropped"}
        except Exception as e:
            logger.error("Error dropping workspace '%s': %s", ws, e)
            return {"status": "error", "message": str(e)}
