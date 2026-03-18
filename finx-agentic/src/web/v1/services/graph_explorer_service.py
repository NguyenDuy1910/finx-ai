"""Graph explorer service — CRUD and query operations on the knowledge graph."""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.graph.client import GraphitiClient

logger = logging.getLogger(__name__)


def _node_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a raw Cypher node record into a JSON-friendly dict."""
    attrs = row.get("attributes") or "{}"
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except (json.JSONDecodeError, TypeError):
            attrs = {}
    return {
        "uuid": row.get("uuid", ""),
        "name": row.get("name", ""),
        "summary": row.get("summary", ""),
        "group_id": row.get("group_id", ""),
        "attributes": attrs,
        "created_at": row.get("created_at", ""),
    }


class GraphExplorerService:
    """Lightweight admin explorer using direct Cypher queries.

    Replaces the old ``GraphMutations``-backed implementation with
    direct FalkorDB driver calls.
    """

    def __init__(self, client: GraphitiClient):
        self._client = client

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    async def _execute(self, cypher: str, **params: Any) -> List[Dict[str, Any]]:
        result = await self._client.graphiti.driver.execute_query(cypher, **params)
        if result is None:
            return []
        # FalkorDB driver returns list of lists or list of dicts depending on version
        if isinstance(result, list):
            return result
        return []

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    async def list_nodes(
        self,
        label: str,
        offset: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        if search:
            cypher = (
                f"MATCH (n:{label}) "
                f"WHERE toLower(n.name) CONTAINS toLower($search) "
                f"RETURN n ORDER BY n.name SKIP $offset LIMIT $limit"
            )
            rows = await self._execute(cypher, search=search, offset=offset, limit=limit)
        else:
            cypher = (
                f"MATCH (n:{label}) "
                f"RETURN n ORDER BY n.name SKIP $offset LIMIT $limit"
            )
            rows = await self._execute(cypher, offset=offset, limit=limit)

        count_cypher = f"MATCH (n:{label}) RETURN count(n) AS cnt"
        count_rows = await self._execute(count_cypher)
        total = count_rows[0].get("cnt", 0) if count_rows else 0

        nodes = []
        for r in rows:
            node_data = r.get("n") if isinstance(r, dict) else r
            if isinstance(node_data, dict):
                nodes.append(_node_record(node_data))
        return {"nodes": nodes, "total": total, "offset": offset, "limit": limit}

    async def get_node(self, label: str, node_uuid: str) -> Optional[Dict[str, Any]]:
        cypher = f"MATCH (n:{label} {{uuid: $uuid}}) RETURN n"
        rows = await self._execute(cypher, uuid=node_uuid)
        if not rows:
            return None
        node_data = rows[0].get("n") if isinstance(rows[0], dict) else rows[0]
        return _node_record(node_data) if isinstance(node_data, dict) else None

    async def create_node(
        self,
        label: str,
        name: str,
        description: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        node_uuid = str(_uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        attrs_json = json.dumps(attributes or {})

        cypher = (
            f"CREATE (n:{label} {{"
            f"  uuid: $uuid, name: $name, summary: $summary,"
            f"  attributes: $attributes, group_id: $group_id,"
            f"  created_at: $created_at"
            f"}}) RETURN n"
        )
        await self._execute(
            cypher,
            uuid=node_uuid,
            name=name,
            summary=description,
            attributes=attrs_json,
            group_id=self._client.group_id,
            created_at=now,
        )
        return {
            "uuid": node_uuid,
            "name": name,
            "summary": description,
            "attributes": attributes or {},
            "created_at": now,
        }

    async def update_node(
        self,
        label: str,
        node_uuid: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        sets: List[str] = []
        params: Dict[str, Any] = {"uuid": node_uuid}
        if name is not None:
            sets.append("n.name = $name")
            params["name"] = name
        if description is not None:
            sets.append("n.summary = $summary")
            params["summary"] = description
        if attributes is not None:
            sets.append("n.attributes = $attributes")
            params["attributes"] = json.dumps(attributes)
        if not sets:
            return await self.get_node(label, node_uuid)

        cypher = f"MATCH (n:{label} {{uuid: $uuid}}) SET {', '.join(sets)} RETURN n"
        rows = await self._execute(cypher, **params)
        if not rows:
            return None
        node_data = rows[0].get("n") if isinstance(rows[0], dict) else rows[0]
        return _node_record(node_data) if isinstance(node_data, dict) else None

    async def delete_node(self, label: str, node_uuid: str) -> bool:
        cypher = f"MATCH (n:{label} {{uuid: $uuid}}) DETACH DELETE n"
        await self._execute(cypher, uuid=node_uuid)
        return True

    # ------------------------------------------------------------------
    # Edge CRUD
    # ------------------------------------------------------------------

    async def list_edges(
        self,
        source_uuid: Optional[str] = None,
        target_uuid: Optional[str] = None,
        edge_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        where_clauses: List[str] = []
        params: Dict[str, Any] = {"offset": offset, "limit": limit}

        if source_uuid:
            where_clauses.append("src.uuid = $source_uuid")
            params["source_uuid"] = source_uuid
        if target_uuid:
            where_clauses.append("tgt.uuid = $target_uuid")
            params["target_uuid"] = target_uuid

        rel_pattern = f"[r:{edge_type}]" if edge_type else "[r]"
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        cypher = (
            f"MATCH (src)-{rel_pattern}->(tgt) {where_clause} "
            f"RETURN r, src.uuid AS source_uuid, src.name AS source_name, "
            f"tgt.uuid AS target_uuid, tgt.name AS target_name, type(r) AS rel_type "
            f"SKIP $offset LIMIT $limit"
        )
        rows = await self._execute(cypher, **params)

        edges = []
        for r in rows:
            if isinstance(r, dict):
                edges.append({
                    "uuid": r.get("r", {}).get("uuid", "") if isinstance(r.get("r"), dict) else "",
                    "source_uuid": r.get("source_uuid", ""),
                    "source_name": r.get("source_name", ""),
                    "target_uuid": r.get("target_uuid", ""),
                    "target_name": r.get("target_name", ""),
                    "type": r.get("rel_type", ""),
                    "fact": r.get("r", {}).get("fact", "") if isinstance(r.get("r"), dict) else "",
                })
        return {"edges": edges, "offset": offset, "limit": limit}

    async def get_edge(self, edge_uuid: str) -> Optional[Dict[str, Any]]:
        cypher = (
            "MATCH (src)-[r]->(tgt) WHERE r.uuid = $uuid "
            "RETURN r, src.uuid AS source_uuid, src.name AS source_name, "
            "tgt.uuid AS target_uuid, tgt.name AS target_name, type(r) AS rel_type"
        )
        rows = await self._execute(cypher, uuid=edge_uuid)
        if not rows:
            return None
        r = rows[0]
        if isinstance(r, dict):
            return {
                "uuid": edge_uuid,
                "source_uuid": r.get("source_uuid", ""),
                "source_name": r.get("source_name", ""),
                "target_uuid": r.get("target_uuid", ""),
                "target_name": r.get("target_name", ""),
                "type": r.get("rel_type", ""),
                "fact": r.get("r", {}).get("fact", "") if isinstance(r.get("r"), dict) else "",
            }
        return None

    async def create_edge(
        self,
        source_uuid: str,
        target_uuid: str,
        edge_type: str,
        fact: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        edge_uuid = str(_uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        attrs_json = json.dumps(attributes or {})
        cypher = (
            f"MATCH (src {{uuid: $source_uuid}}), (tgt {{uuid: $target_uuid}}) "
            f"CREATE (src)-[r:{edge_type} {{"
            f"  uuid: $uuid, fact: $fact, attributes: $attributes,"
            f"  group_id: $group_id, created_at: $created_at,"
            f"  source_node_uuid: $source_uuid, target_node_uuid: $target_uuid"
            f"}}]->(tgt) RETURN r"
        )
        await self._execute(
            cypher,
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            uuid=edge_uuid,
            fact=fact,
            attributes=attrs_json,
            group_id=self._client.group_id,
            created_at=now,
        )
        return {
            "uuid": edge_uuid,
            "source_uuid": source_uuid,
            "target_uuid": target_uuid,
            "type": edge_type,
            "fact": fact,
            "created_at": now,
        }

    async def update_edge(
        self,
        edge_uuid: str,
        fact: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        sets: List[str] = []
        params: Dict[str, Any] = {"uuid": edge_uuid}
        if fact is not None:
            sets.append("r.fact = $fact")
            params["fact"] = fact
        if attributes is not None:
            sets.append("r.attributes = $attributes")
            params["attributes"] = json.dumps(attributes)
        if not sets:
            return await self.get_edge(edge_uuid)

        cypher = (
            f"MATCH (src)-[r]->(tgt) WHERE r.uuid = $uuid "
            f"SET {', '.join(sets)} "
            f"RETURN r, src.uuid AS source_uuid, tgt.uuid AS target_uuid, type(r) AS rel_type"
        )
        rows = await self._execute(cypher, **params)
        if not rows:
            return None
        r = rows[0]
        if isinstance(r, dict):
            return {
                "uuid": edge_uuid,
                "source_uuid": r.get("source_uuid", ""),
                "target_uuid": r.get("target_uuid", ""),
                "type": r.get("rel_type", ""),
                "fact": fact or "",
            }
        return None

    async def delete_edge(self, edge_uuid: str) -> bool:
        cypher = "MATCH ()-[r]->() WHERE r.uuid = $uuid DELETE r"
        await self._execute(cypher, uuid=edge_uuid)
        return True

    # ------------------------------------------------------------------
    # Exploration / graph traversal
    # ------------------------------------------------------------------

    async def explore_node(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        """Get a node with its immediate neighbours (1-hop)."""
        node = await self.get_node("", node_uuid)
        if node is None:
            # Try without label constraint
            cypher = "MATCH (n {uuid: $uuid}) RETURN n, labels(n) AS labels"
            rows = await self._execute(cypher, uuid=node_uuid)
            if not rows:
                return None
            r = rows[0]
            node_data = r.get("n") if isinstance(r, dict) else r
            node = _node_record(node_data) if isinstance(node_data, dict) else {}
            node["labels"] = r.get("labels", []) if isinstance(r, dict) else []

        # Outgoing edges
        out_cypher = (
            "MATCH (n {uuid: $uuid})-[r]->(m) "
            "RETURN type(r) AS rel_type, r.uuid AS edge_uuid, "
            "m.uuid AS target_uuid, m.name AS target_name, labels(m) AS target_labels"
        )
        out_rows = await self._execute(out_cypher, uuid=node_uuid)

        # Incoming edges
        in_cypher = (
            "MATCH (n {uuid: $uuid})<-[r]-(m) "
            "RETURN type(r) AS rel_type, r.uuid AS edge_uuid, "
            "m.uuid AS source_uuid, m.name AS source_name, labels(m) AS source_labels"
        )
        in_rows = await self._execute(in_cypher, uuid=node_uuid)

        return {
            "node": node,
            "outgoing": [r for r in out_rows if isinstance(r, dict)],
            "incoming": [r for r in in_rows if isinstance(r, dict)],
        }

    async def expand_node(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        """Alias for explore_node — returns 1-hop neighbourhood."""
        return await self.explore_node(node_uuid)

    async def get_lineage(self, node_uuid: str) -> Dict[str, Any]:
        """Trace all ancestors (incoming) up to 5 hops."""
        cypher = (
            "MATCH path = (n {uuid: $uuid})<-[*1..5]-(ancestor) "
            "RETURN [node IN nodes(path) | {uuid: node.uuid, name: node.name, labels: labels(node)}] AS chain "
            "LIMIT 50"
        )
        rows = await self._execute(cypher, uuid=node_uuid)
        chains = [r.get("chain", []) for r in rows if isinstance(r, dict)]
        return {"node_uuid": node_uuid, "lineage_chains": chains}

    async def get_overview(self) -> Dict[str, Any]:
        """Return per-label node counts."""
        cypher = (
            "MATCH (n) "
            "RETURN labels(n) AS label, count(n) AS count "
            "ORDER BY count DESC"
        )
        rows = await self._execute(cypher)
        labels = {}
        for r in rows:
            if isinstance(r, dict):
                lbl = r.get("label", ["Unknown"])
                lbl_str = lbl[0] if isinstance(lbl, list) and lbl else str(lbl)
                labels[lbl_str] = r.get("count", 0)
        return {"labels": labels}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_nodes(
        self,
        query: str,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Text-based substring search on node names."""
        if label:
            cypher = (
                f"MATCH (n:{label}) WHERE toLower(n.name) CONTAINS toLower($query) "
                f"RETURN n ORDER BY n.name LIMIT $limit"
            )
        else:
            cypher = (
                "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($query) "
                "RETURN n ORDER BY n.name LIMIT $limit"
            )
        rows = await self._execute(cypher, query=query, limit=limit)
        nodes = []
        for r in rows:
            node_data = r.get("n") if isinstance(r, dict) else r
            if isinstance(node_data, dict):
                nodes.append(_node_record(node_data))
        return {"nodes": nodes, "query": query}

    async def search_nodes_by_embedding(
        self,
        query: str,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Vector similarity search using embeddings."""
        embedding = await self._client.embedder.create(input_data=[query])
        target_label = label or "Table"
        cypher = (
            f"CALL db.idx.vector.queryNodes('{target_label}', 'embedding', $k, vecf32($embedding)) "
            f"YIELD node, score "
            f"RETURN node, score ORDER BY score DESC"
        )
        rows = await self._execute(cypher, k=limit, embedding=embedding)
        nodes = []
        for r in rows:
            if isinstance(r, dict):
                nd = r.get("node", {})
                entry = _node_record(nd) if isinstance(nd, dict) else {}
                entry["score"] = r.get("score", 0.0)
                nodes.append(entry)
        return {"nodes": nodes, "query": query}
