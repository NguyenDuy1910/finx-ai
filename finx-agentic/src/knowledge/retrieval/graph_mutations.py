import json
import logging
import time
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph.cost_tracker import EmbeddingCall
from src.knowledge.graph.schemas.enums import NodeLabel
from src.knowledge.graph.schemas.edges.edge_types import EdgeType
from src.core.cost_tracker import estimate_cost

logger = logging.getLogger(__name__)

VALID_LABELS = {label.value for label in NodeLabel}
VALID_EDGE_TYPES = {et.value for et in EdgeType}


class GraphMutations:

    def __init__(self, client: GraphitiClient):
        self._client = client

    @property
    def _driver(self):
        return self._client.graphiti.driver

    @property
    def _embedder(self):
        _ = self._client.graphiti
        return self._client._embedder

    @property
    def _group_id(self) -> str:
        return self._client.group_id

    async def _execute(self, query: str, **kwargs) -> List[Dict]:
        result = await self._driver.execute_query(query, **kwargs)
        if result is None:
            return []
        records, _, _ = result
        return records or []

    async def _embed(self, text: str) -> List[float]:
        cleaned = text.replace("\n", " ").strip()
        if not cleaned:
            return []
        return await self._embedder.create(input_data=[cleaned])

    def _track_embedding_cost(
        self, label: str, name: str, description: str, duration: float
    ) -> None:
        estimated_tokens = max(1, len(description) // 4)
        cost = estimate_cost(
            self._client.cost_tracker.embedding_model, estimated_tokens, 0,
        ) or 0.0
        self._client.cost_tracker.add(EmbeddingCall(
            node_label=label,
            node_name=name,
            text_length=len(description),
            estimated_tokens=estimated_tokens,
            cost_usd=cost,
            duration_s=duration,
        ))

    @staticmethod
    def _parse_node(row: Dict) -> Dict[str, Any]:
        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "label": row.get("label", ""),
            "summary": row.get("summary", ""),
            "attributes": json.loads(row["attributes"]) if row.get("attributes") else {},
            "created_at": row.get("created_at"),
        }

    @staticmethod
    def _parse_edge(row: Dict) -> Dict[str, Any]:
        return {
            "uuid": row["uuid"],
            "edge_type": row.get("edge_type", ""),
            "fact": row.get("fact", ""),
            "attributes": json.loads(row["attributes"]) if row.get("attributes") else {},
            "source_node": {
                "uuid": row.get("source_uuid", ""),
                "name": row.get("source_name", ""),
                "label": row.get("source_label", ""),
                "summary": row.get("source_summary", ""),
                "attributes": json.loads(row["source_attributes"]) if row.get("source_attributes") else {},
            },
            "target_node": {
                "uuid": row.get("target_uuid", ""),
                "name": row.get("target_name", ""),
                "label": row.get("target_label", ""),
                "summary": row.get("target_summary", ""),
                "attributes": json.loads(row["target_attributes"]) if row.get("target_attributes") else {},
            },
        }

    async def list_nodes(
        self,
        label: str,
        offset: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        if label not in VALID_LABELS:
            raise ValueError(f"Invalid label: {label}")

        count_query = f"MATCH (n:{label} {{group_id: $group_id}}) "
        data_query = f"MATCH (n:{label} {{group_id: $group_id}}) "
        params: Dict[str, Any] = {"group_id": self._group_id}

        if search:
            filter_clause = "WHERE toLower(n.name) CONTAINS toLower($search) OR toLower(n.summary) CONTAINS toLower($search) "
            count_query += filter_clause
            data_query += filter_clause
            params["search"] = search

        count_query += "RETURN count(n) AS total"
        data_query += (
            "RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary, "
            "n.attributes AS attributes, n.created_at AS created_at "
            "ORDER BY n.name SKIP $offset LIMIT $limit"
        )
        params["offset"] = offset
        params["limit"] = limit

        count_records = await self._execute(count_query, **params)
        total = count_records[0]["total"] if count_records else 0

        records = await self._execute(data_query, **params)
        nodes = []
        for r in records:
            node = self._parse_node(r)
            node["label"] = label
            nodes.append(node)

        return {"nodes": nodes, "total": total, "offset": offset, "limit": limit}

    async def get_node(self, label: str, node_uuid: str) -> Optional[Dict[str, Any]]:
        if label not in VALID_LABELS:
            raise ValueError(f"Invalid label: {label}")

        records = await self._execute(
            f"""
            MATCH (n:{label} {{uuid: $uuid, group_id: $group_id}})
            RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
                   n.attributes AS attributes, n.created_at AS created_at
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        if not records:
            return None
        node = self._parse_node(records[0])
        node["label"] = label
        return node

    async def create_node(
        self,
        label: str,
        name: str,
        description: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if label not in VALID_LABELS:
            raise ValueError(f"Invalid label: {label}")

        node_uuid = str(uuid_lib.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        attrs = json.dumps(attributes or {})

        start = time.monotonic()
        embedding = await self._embed(description) if description else []
        embed_duration = time.monotonic() - start

        if description:
            self._track_embedding_cost(label, name, description, embed_duration)

        await self._execute(
            f"""
            MERGE (n:{label} {{name: $name, group_id: $group_id}})
            SET n.uuid       = $uuid,
                n.summary    = $summary,
                n.attributes = $attributes,
                n.created_at = $created_at,
                n.embedding  = vecf32($embedding)
            """,
            uuid=node_uuid,
            name=name,
            group_id=self._group_id,
            summary=description,
            attributes=attrs,
            created_at=now,
            embedding=embedding,
        )

        return {
            "uuid": node_uuid,
            "name": name,
            "label": label,
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
        if label not in VALID_LABELS:
            raise ValueError(f"Invalid label: {label}")

        set_clauses = []
        params: Dict[str, Any] = {"uuid": node_uuid, "group_id": self._group_id}

        if name is not None:
            set_clauses.append("n.name = $name")
            params["name"] = name
        if description is not None:
            set_clauses.append("n.summary = $summary")
            params["summary"] = description
        if attributes is not None:
            set_clauses.append("n.attributes = $attributes")
            params["attributes"] = json.dumps(attributes)

        if not set_clauses:
            return await self.get_node(label, node_uuid)

        needs_reindex = name is not None or description is not None
        if needs_reindex:
            existing = await self.get_node(label, node_uuid)
            embed_text = description if description is not None else (existing["summary"] if existing else "")
            resolved_name = name if name is not None else (existing["name"] if existing else "")

            start = time.monotonic()
            embedding = await self._embed(embed_text) if embed_text else []
            embed_duration = time.monotonic() - start

            set_clauses.append("n.embedding = vecf32($embedding)")
            params["embedding"] = embedding

            if embed_text:
                self._track_embedding_cost(label, resolved_name, embed_text, embed_duration)

        query = (
            f"MATCH (n:{label} {{uuid: $uuid, group_id: $group_id}}) "
            f"SET {', '.join(set_clauses)} "
            "RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary, "
            "n.attributes AS attributes, n.created_at AS created_at"
        )

        records = await self._execute(query, **params)
        if not records:
            return None
        node = self._parse_node(records[0])
        node["label"] = label
        return node

    async def delete_node(self, label: str, node_uuid: str) -> bool:
        if label not in VALID_LABELS:
            raise ValueError(f"Invalid label: {label}")

        records = await self._execute(
            f"""
            MATCH (n:{label} {{uuid: $uuid, group_id: $group_id}})
            DETACH DELETE n
            RETURN count(n) AS deleted
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        return bool(records)

    async def list_edges(
        self,
        source_uuid: Optional[str] = None,
        target_uuid: Optional[str] = None,
        edge_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        match_clause = "MATCH (source)-[r]->(target) "
        where_clauses = ["r.group_id = $group_id"]
        params: Dict[str, Any] = {"group_id": self._group_id}

        if source_uuid:
            where_clauses.append("source.uuid = $source_uuid")
            params["source_uuid"] = source_uuid
        if target_uuid:
            where_clauses.append("target.uuid = $target_uuid")
            params["target_uuid"] = target_uuid
        if edge_type:
            where_clauses.append("type(r) = $edge_type")
            params["edge_type"] = edge_type

        where_clause = "WHERE " + " AND ".join(where_clauses) + " " if where_clauses else ""

        count_query = match_clause + where_clause + "RETURN count(r) AS total"
        count_records = await self._execute(count_query, **params)
        total = count_records[0]["total"] if count_records else 0

        data_query = (
            match_clause + where_clause +
            "RETURN r.uuid AS uuid, type(r) AS edge_type, r.fact AS fact, "
            "r.attributes AS attributes, "
            "source.uuid AS source_uuid, source.name AS source_name, "
            "source.summary AS source_summary, source.attributes AS source_attributes, "
            "head(labels(source)) AS source_label, "
            "target.uuid AS target_uuid, target.name AS target_name, "
            "target.summary AS target_summary, target.attributes AS target_attributes, "
            "head(labels(target)) AS target_label "
            "ORDER BY r.created_at DESC SKIP $offset LIMIT $limit"
        )
        params["offset"] = offset
        params["limit"] = limit

        records = await self._execute(data_query, **params)
        edges = [self._parse_edge(r) for r in records]

        return {"edges": edges, "total": total, "offset": offset, "limit": limit}

    async def get_edge(self, edge_uuid: str) -> Optional[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (source)-[r]->(target)
            WHERE r.uuid = $uuid AND r.group_id = $group_id
            RETURN r.uuid AS uuid, type(r) AS edge_type, r.fact AS fact,
                   r.attributes AS attributes,
                   source.uuid AS source_uuid, source.name AS source_name,
                   source.summary AS source_summary, source.attributes AS source_attributes,
                   head(labels(source)) AS source_label,
                   target.uuid AS target_uuid, target.name AS target_name,
                   target.summary AS target_summary, target.attributes AS target_attributes,
                   head(labels(target)) AS target_label
            """,
            uuid=edge_uuid,
            group_id=self._group_id,
        )
        if not records:
            return None
        return self._parse_edge(records[0])

    async def create_edge(
        self,
        source_uuid: str,
        target_uuid: str,
        edge_type: str,
        fact: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if edge_type not in VALID_EDGE_TYPES:
            raise ValueError(f"Invalid edge_type: {edge_type}")

        edge_uuid = str(uuid_lib.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        attrs = json.dumps(attributes or {})

        records = await self._execute(
            f"""
            MATCH (source {{uuid: $source_uuid}})
            MATCH (target {{uuid: $target_uuid}})
            MERGE (source)-[r:{edge_type} {{
                source_node_uuid: $source_uuid,
                target_node_uuid: $target_uuid
            }}]->(target)
            SET r.uuid       = $uuid,
                r.group_id   = $group_id,
                r.fact       = $fact,
                r.attributes = $attributes,
                r.created_at = $created_at
            RETURN r.uuid AS uuid, type(r) AS edge_type, r.fact AS fact,
                   r.attributes AS attributes,
                   source.uuid AS source_uuid, source.name AS source_name,
                   source.summary AS source_summary, source.attributes AS source_attributes,
                   head(labels(source)) AS source_label,
                   target.uuid AS target_uuid, target.name AS target_name,
                   target.summary AS target_summary, target.attributes AS target_attributes,
                   head(labels(target)) AS target_label
            """,
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            uuid=edge_uuid,
            group_id=self._group_id,
            fact=fact,
            attributes=attrs,
            created_at=now,
        )

        if not records:
            raise ValueError("Source or target node not found")
        return self._parse_edge(records[0])

    async def update_edge(
        self,
        edge_uuid: str,
        fact: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        set_clauses = []
        params: Dict[str, Any] = {"uuid": edge_uuid, "group_id": self._group_id}

        if fact is not None:
            set_clauses.append("r.fact = $fact")
            params["fact"] = fact
        if attributes is not None:
            set_clauses.append("r.attributes = $attributes")
            params["attributes"] = json.dumps(attributes)

        if not set_clauses:
            return await self.get_edge(edge_uuid)

        query = (
            "MATCH (source)-[r]->(target) "
            "WHERE r.uuid = $uuid AND r.group_id = $group_id "
            f"SET {', '.join(set_clauses)} "
            "RETURN r.uuid AS uuid, type(r) AS edge_type, r.fact AS fact, "
            "r.attributes AS attributes, "
            "source.uuid AS source_uuid, source.name AS source_name, "
            "source.summary AS source_summary, source.attributes AS source_attributes, "
            "head(labels(source)) AS source_label, "
            "target.uuid AS target_uuid, target.name AS target_name, "
            "target.summary AS target_summary, target.attributes AS target_attributes, "
            "head(labels(target)) AS target_label"
        )

        records = await self._execute(query, **params)
        if not records:
            return None
        return self._parse_edge(records[0])

    async def delete_edge(self, edge_uuid: str) -> bool:
        records = await self._execute(
            """
            MATCH ()-[r]->()
            WHERE r.uuid = $uuid AND r.group_id = $group_id
            DELETE r
            RETURN count(r) AS deleted
            """,
            uuid=edge_uuid,
            group_id=self._group_id,
        )
        return bool(records)

    async def explore_node(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        center_records = await self._execute(
            """
            MATCH (n {uuid: $uuid, group_id: $group_id})
            RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
                   n.attributes AS attributes, n.created_at AS created_at,
                   head(labels(n)) AS label
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        if not center_records:
            return None

        center = self._parse_node(center_records[0])
        center["label"] = center_records[0].get("label", "")

        neighbor_records = await self._execute(
            """
            MATCH (n {uuid: $uuid})-[r]-(neighbor)
            WHERE neighbor.group_id = $group_id
            RETURN DISTINCT neighbor.uuid AS uuid, neighbor.name AS name,
                   neighbor.summary AS summary, neighbor.attributes AS attributes,
                   neighbor.created_at AS created_at, head(labels(neighbor)) AS label
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        neighbors = []
        for r in neighbor_records:
            node = self._parse_node(r)
            node["label"] = r.get("label", "")
            neighbors.append(node)

        edge_records = await self._execute(
            """
            MATCH (n {uuid: $uuid})-[r]-(other)
            WHERE other.group_id = $group_id
            WITH r, startNode(r) AS source, endNode(r) AS target
            RETURN r.uuid AS uuid, type(r) AS edge_type, r.fact AS fact,
                   r.attributes AS attributes,
                   source.uuid AS source_uuid, source.name AS source_name,
                   source.summary AS source_summary, source.attributes AS source_attributes,
                   head(labels(source)) AS source_label,
                   target.uuid AS target_uuid, target.name AS target_name,
                   target.summary AS target_summary, target.attributes AS target_attributes,
                   head(labels(target)) AS target_label
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        edges = [self._parse_edge(r) for r in edge_records]

        return {"center": center, "neighbors": neighbors, "edges": edges}

    async def expand_node(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        return await self.explore_node(node_uuid)

    async def get_lineage(self, node_uuid: str, max_depth: int = 5) -> Dict[str, Any]:
        records = await self._execute(
            """
            MATCH path = (start {uuid: $uuid})-[*1..5]-(end)
            WHERE ALL(n IN nodes(path) WHERE n.group_id = $group_id)
            UNWIND nodes(path) AS n
            WITH DISTINCT n
            RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
                   n.attributes AS attributes, n.created_at AS created_at,
                   head(labels(n)) AS label
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        nodes = []
        for r in records:
            node = self._parse_node(r)
            node["label"] = r.get("label", "")
            nodes.append(node)

        edge_records = await self._execute(
            """
            MATCH path = (start {uuid: $uuid})-[*1..5]-(end)
            WHERE ALL(n IN nodes(path) WHERE n.group_id = $group_id)
            UNWIND relationships(path) AS r
            WITH DISTINCT r, startNode(r) AS source, endNode(r) AS target
            RETURN r.uuid AS uuid, type(r) AS edge_type, r.fact AS fact,
                   r.attributes AS attributes,
                   source.uuid AS source_uuid, source.name AS source_name,
                   source.summary AS source_summary, source.attributes AS source_attributes,
                   head(labels(source)) AS source_label,
                   target.uuid AS target_uuid, target.name AS target_name,
                   target.summary AS target_summary, target.attributes AS target_attributes,
                   head(labels(target)) AS target_label
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        edges = [self._parse_edge(r) for r in edge_records]

        path_records = await self._execute(
            """
            MATCH path = (start {uuid: $uuid})-[*1..5]-(end)
            WHERE ALL(n IN nodes(path) WHERE n.group_id = $group_id)
            RETURN [n IN nodes(path) | n.uuid] AS path_uuids
            LIMIT 20
            """,
            uuid=node_uuid,
            group_id=self._group_id,
        )
        paths = [r["path_uuids"] for r in path_records if r.get("path_uuids")]

        return {"nodes": nodes, "edges": edges, "paths": paths}

    async def get_overview(self) -> Dict[str, Any]:
        domain_records = await self._execute(
            """
            MATCH (d:Domain {group_id: $group_id})
            OPTIONAL MATCH (t:Table)-[:BELONGS_TO_DOMAIN]->(d)
            OPTIONAL MATCH (d)-[:CONTAINS_ENTITY]->(e:BusinessEntity)
            RETURN d.uuid AS uuid, d.name AS name,
                   count(DISTINCT t) AS table_count,
                   count(DISTINCT e) AS entity_count
            ORDER BY d.name
            """,
            group_id=self._group_id,
        )
        domains = [
            {
                "uuid": r["uuid"],
                "name": r["name"],
                "table_count": r.get("table_count", 0),
                "entity_count": r.get("entity_count", 0),
            }
            for r in domain_records
        ]

        stats: Dict[str, int] = {}
        for label in NodeLabel:
            count_records = await self._execute(
                f"MATCH (n:{label.value} {{group_id: $group_id}}) RETURN count(n) AS cnt",
                group_id=self._group_id,
            )
            stats[label.value] = count_records[0]["cnt"] if count_records else 0

        return {"domains": domains, "stats": stats}

    async def search_nodes(
        self,
        query: str,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        if label and label not in VALID_LABELS:
            raise ValueError(f"Invalid label: {label}")

        if label:
            match_clause = f"MATCH (n:{label} {{group_id: $group_id}}) "
        else:
            match_clause = "MATCH (n {group_id: $group_id}) "

        search_query = (
            match_clause +
            "WHERE toLower(n.name) CONTAINS toLower($search_term) "
            "OR toLower(n.summary) CONTAINS toLower($search_term) "
            "RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary, "
            "n.attributes AS attributes, n.created_at AS created_at, "
            "head(labels(n)) AS label "
            "ORDER BY n.name LIMIT $limit"
        )

        records = await self._execute(
            search_query,
            group_id=self._group_id,
            search_term=query,
            limit=limit,
        )
        nodes = []
        for r in records:
            node = self._parse_node(r)
            node["label"] = r.get("label", "")
            nodes.append(node)

        return {"nodes": nodes, "total": len(nodes)}

    async def search_nodes_by_embedding(
        self,
        query: str,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        if label and label not in VALID_LABELS:
            raise ValueError(f"Invalid label: {label}")

        query_embedding = await self._embed(query)
        if not query_embedding:
            return await self.search_nodes(query, label, limit)

        target_label = label or "Table"
        if target_label not in {lbl for lbl in GraphitiClient._VECTOR_LABELS}:
            return await self.search_nodes(query, label, limit)

        vector_query = (
            f"MATCH (n:{target_label} {{group_id: $group_id}}) "
            "WHERE n.embedding IS NOT NULL "
            "WITH n, (2 - vec.cosineDistance(n.embedding, vecf32($embedding))) / 2 AS score "
            "WHERE score >= 0.3 "
            "RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary, "
            "n.attributes AS attributes, n.created_at AS created_at, "
            f"'{target_label}' AS label, score "
            "ORDER BY score DESC LIMIT $limit"
        )

        records = await self._execute(
            vector_query,
            group_id=self._group_id,
            embedding=query_embedding,
            limit=limit,
        )
        nodes = []
        for r in records:
            node = self._parse_node(r)
            node["label"] = r.get("label", target_label)
            node["score"] = r.get("score", 0.0)
            nodes.append(node)

        return {"nodes": nodes, "total": len(nodes)}
