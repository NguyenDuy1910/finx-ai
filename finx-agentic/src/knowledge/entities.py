import json
import logging
from typing import Any, Dict, List, Optional

from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

from src.knowledge.client import GraphitiClient
from src.knowledge.models.nodes import (
    BusinessEntityNode,
    ColumnNode,
    NodeLabel,
    QueryPatternNode,
    TableNode,
)
from src.knowledge.models.edges import (
    EdgeType,
    EntityMappingEdge,
    ForeignKeyEdge,
    HasColumnEdge,
    JoinEdge,
    QueryPatternEdge,
    SynonymEdge,
)

logger = logging.getLogger(__name__)


class EntityRegistry:
    """High-level façade over the graph's entity & edge layer."""

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

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> List[float]:
        cleaned = text.replace("\n", " ").strip()
        if not cleaned:
            return []
        return await self._embedder.create(input_data=[cleaned])

    async def _execute(self, query: str, **kwargs) -> List[Dict]:
        result = await self._driver.execute_query(query, **kwargs)
        if result is None:
            return []
        records, _, _ = result
        return records or []

    # ------------------------------------------------------------------
    # register / upsert entities
    # ------------------------------------------------------------------

    async def register_table(self, table: TableNode) -> EntityNode:
        """Upsert a Table entity node."""
        entity = table.to_entity_node(self._group_id)
        return await self._upsert_entity(entity, NodeLabel.TABLE)

    async def register_column(self, column: ColumnNode) -> EntityNode:
        """Upsert a Column entity node."""
        entity = column.to_entity_node(self._group_id)
        return await self._upsert_entity(entity, NodeLabel.COLUMN)

    async def register_business_entity(self, entity_model: BusinessEntityNode) -> EntityNode:
        """Upsert a BusinessEntity node."""
        entity = entity_model.to_entity_node(self._group_id)
        return await self._upsert_entity(entity, NodeLabel.BUSINESS_ENTITY)

    async def register_query_pattern(self, pattern: QueryPatternNode) -> EntityNode:
        """Upsert a QueryPattern node."""
        entity = pattern.to_entity_node(self._group_id)
        return await self._upsert_entity(entity, NodeLabel.QUERY_PATTERN)

    async def _upsert_entity(self, node: EntityNode, label: NodeLabel) -> EntityNode:
        description = (node.summary or "").replace("\n", " ").strip()
        embedding = await self._embed(description) if description else []

        await self._execute(
            f"""
            MERGE (n:{label.value} {{name: $name, group_id: $group_id}})
            SET n.uuid       = $uuid,
                n.created_at = $created_at,
                n.summary    = $summary,
                n.attributes = $attributes,
                n.embedding  = vecf32($embedding)
            """,
            uuid=node.uuid,
            name=node.name,
            group_id=node.group_id,
            created_at=node.created_at.isoformat(),
            summary=node.summary or "",
            attributes=json.dumps(node.attributes or {}),
            embedding=embedding,
        )
        logger.debug("Upserted entity %s [%s]", node.name, label.value)
        return node

    # ------------------------------------------------------------------
    # register edges
    # ------------------------------------------------------------------

    async def register_has_column(
        self, edge: HasColumnEdge, table_uuid: str, column_uuid: str
    ) -> None:
        entity_edge = edge.to_entity_edge(table_uuid, column_uuid, self._group_id)
        await self._upsert_edge(entity_edge)

    async def register_join(
        self, edge: JoinEdge, source_uuid: str, target_uuid: str
    ) -> None:
        entity_edge = edge.to_entity_edge(source_uuid, target_uuid, self._group_id)
        await self._upsert_edge(entity_edge)

    async def register_entity_mapping(
        self, edge: EntityMappingEdge, entity_uuid: str, table_uuid: str
    ) -> None:
        entity_edge = edge.to_entity_edge(entity_uuid, table_uuid, self._group_id)
        await self._upsert_edge(entity_edge)

    async def register_foreign_key(
        self, edge: ForeignKeyEdge, source_uuid: str, target_uuid: str
    ) -> None:
        entity_edge = edge.to_entity_edge(source_uuid, target_uuid, self._group_id)
        await self._upsert_edge(entity_edge)

    async def register_synonym(
        self, edge: SynonymEdge, source_uuid: str, target_uuid: str
    ) -> None:
        entity_edge = edge.to_entity_edge(source_uuid, target_uuid, self._group_id)
        await self._upsert_edge(entity_edge)

    async def register_query_pattern_edge(
        self, edge: QueryPatternEdge, pattern_uuid: str, table_uuid: str
    ) -> None:
        entity_edge = edge.to_entity_edge(pattern_uuid, table_uuid, self._group_id)
        await self._upsert_edge(entity_edge)

    async def _upsert_edge(self, edge: EntityEdge) -> None:
        await self._execute(
            f"""
            MATCH (source {{uuid: $source_uuid}})
            MATCH (target {{uuid: $target_uuid}})
            MERGE (source)-[r:{edge.name} {{
                source_node_uuid: $source_uuid,
                target_node_uuid: $target_uuid
            }}]->(target)
            SET r.uuid       = $uuid,
                r.group_id   = $group_id,
                r.created_at = $created_at,
                r.fact       = $fact,
                r.attributes = $attributes
            """,
            source_uuid=edge.source_node_uuid,
            target_uuid=edge.target_node_uuid,
            uuid=edge.uuid,
            group_id=edge.group_id,
            created_at=edge.created_at.isoformat(),
            fact=edge.fact or "",
            attributes=json.dumps(edge.attributes or {}),
        )
        logger.debug("Upserted edge %s -> %s [%s]", edge.source_node_uuid, edge.target_node_uuid, edge.name)

    # ------------------------------------------------------------------
    # lookups
    # ------------------------------------------------------------------

    async def get_table(self, table_name: str, database: Optional[str] = None) -> Optional[Dict]:
        if database:
            name = f"{database}.{table_name}"
        else:
            name = table_name

        records = await self._execute(
            """
            MATCH (t:Table)
            WHERE t.name = $name OR t.name CONTAINS $table_name
            RETURN t.uuid AS uuid,
                   t.name AS name,
                   t.summary AS summary,
                   t.attributes AS attributes
            LIMIT 1
            """,
            name=name,
            table_name=table_name,
        )
        if not records:
            return None
        row = records[0]
        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "summary": row.get("summary", ""),
            "attributes": json.loads(row["attributes"]) if row.get("attributes") else {},
        }

    async def get_all_tables(self, database: Optional[str] = None, offset: int = 0, limit: int = 50) -> List[Dict]:
        if database:
            records = await self._execute(
                """
                MATCH (t:Table)
                WHERE t.name STARTS WITH $prefix
                RETURN t.uuid AS uuid, t.name AS name, t.summary AS summary, t.attributes AS attributes
                ORDER BY t.name
                SKIP $offset LIMIT $limit
                """,
                prefix=f"{database}.",
                offset=offset,
                limit=limit,
            )
        else:
            records = await self._execute(
                """
                MATCH (t:Table)
                RETURN t.uuid AS uuid, t.name AS name, t.summary AS summary, t.attributes AS attributes
                ORDER BY t.name
                SKIP $offset LIMIT $limit
                """,
                offset=offset,
                limit=limit,
            )
        return [
            {
                "uuid": r["uuid"],
                "name": r["name"],
                "summary": r.get("summary", ""),
                "attributes": json.loads(r["attributes"]) if r.get("attributes") else {},
            }
            for r in records
        ]

    async def get_all_entities(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (e:BusinessEntity)
            RETURN e.uuid AS uuid, e.name AS name, e.summary AS summary, e.attributes AS attributes
            ORDER BY e.name
            SKIP $offset LIMIT $limit
            """,
            offset=offset,
            limit=limit,
        )
        return [
            {
                "uuid": r["uuid"],
                "name": r["name"],
                "summary": r.get("summary", ""),
                "attributes": json.loads(r["attributes"]) if r.get("attributes") else {},
            }
            for r in records
        ]

    async def get_all_patterns(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (p:QueryPattern)
            RETURN p.uuid AS uuid, p.name AS name, p.summary AS summary, p.attributes AS attributes
            ORDER BY p.name
            SKIP $offset LIMIT $limit
            """,
            offset=offset,
            limit=limit,
        )
        return [
            {
                "uuid": r["uuid"],
                "name": r["name"],
                "summary": r.get("summary", ""),
                "attributes": json.loads(r["attributes"]) if r.get("attributes") else {},
            }
            for r in records
        ]

    async def get_columns_for_table(self, table_name: str, database: Optional[str] = None) -> List[Dict]:
        """Return all columns belonging to a table."""
        full_name = f"{database}.{table_name}" if database else table_name
        records = await self._execute(
            """
            MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
            WHERE t.name = $name OR t.name CONTAINS $table_name
            RETURN c.uuid AS uuid,
                   c.name AS name,
                   c.summary AS summary,
                   c.attributes AS attributes
            """,
            name=full_name,
            table_name=table_name,
        )
        return [
            {
                "uuid": r["uuid"],
                "name": r["name"],
                "summary": r.get("summary", ""),
                "attributes": json.loads(r["attributes"]) if r.get("attributes") else {},
            }
            for r in records
        ]

    # ------------------------------------------------------------------
    # business-term resolution
    # ------------------------------------------------------------------

    async def resolve_term(self, term: str) -> List[Dict[str, Any]]:
        """
        Resolve a business term (e.g. "khách hàng") to mapped tables.

        Searches BusinessEntity nodes by name, synonyms, and then falls back
        to a vector-similarity search.
        """
        # 1. exact / synonym match
        records = await self._execute(
            """
            MATCH (e:BusinessEntity)
            WHERE toLower(e.name) = toLower($term)
                  OR e.attributes CONTAINS $term
            OPTIONAL MATCH (e)-[:ENTITY_MAPPING]->(t:Table)
            RETURN e.name AS entity_name,
                   e.summary AS description,
                   e.attributes AS entity_attrs,
                   collect(DISTINCT t.name) AS tables
            """,
            term=term,
        )
        if records and records[0].get("entity_name"):
            return [self._term_row(r) for r in records]

        # 2. vector fallback
        return await self.search_entities(term)

    async def search_entities(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Semantic search across BusinessEntity nodes."""
        embedding = await self._embed(query)
        if not embedding:
            return []

        records = await self._execute(
            """
            MATCH (e:BusinessEntity {group_id: $group_id})
            WHERE e.embedding IS NOT NULL
            WITH e,
                 (2 - vec.cosineDistance(e.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            OPTIONAL MATCH (e)-[:ENTITY_MAPPING]->(t:Table)
            RETURN e.name AS entity_name,
                   e.summary AS description,
                   e.attributes AS entity_attrs,
                   collect(DISTINCT t.name) AS tables,
                   score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            group_id=self._group_id,
            embedding=embedding,
            threshold=threshold,
            top_k=top_k,
        )
        return [
            {**self._term_row(r), "score": float(r.get("score", 0))}
            for r in records
        ]

    # ------------------------------------------------------------------
    # relationship traversal
    # ------------------------------------------------------------------

    async def find_related_tables(
        self,
        table_name: str,
        database: Optional[str] = None,
        max_depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Find tables related through joins, foreign keys, or shared
        business entities.
        """
        full_name = f"{database}.{table_name}" if database else table_name

        records = await self._execute(
            """
            MATCH (t:Table)
            WHERE t.name = $name OR t.name CONTAINS $table_name
            OPTIONAL MATCH (t)-[r:JOIN|FOREIGN_KEY]-(related:Table)
            OPTIONAL MATCH (e:BusinessEntity)-[:ENTITY_MAPPING]->(t)
            OPTIONAL MATCH (e)-[:ENTITY_MAPPING]->(sibling:Table)
            WHERE sibling <> t
            RETURN t.name AS source,
                   collect(DISTINCT {
                       name: related.name,
                       relationship: type(r),
                       attributes: r.attributes
                   }) AS direct_relations,
                   collect(DISTINCT {
                       name: sibling.name,
                       shared_entity: e.name
                   }) AS entity_relations
            """,
            name=full_name,
            table_name=table_name,
        )
        if not records:
            return []

        row = records[0]
        relations = []

        for rel in row.get("direct_relations", []):
            if rel.get("name"):
                attrs = json.loads(rel["attributes"]) if rel.get("attributes") else {}
                relations.append({
                    "table": rel["name"],
                    "relationship": rel.get("relationship", "RELATED"),
                    "join_type": attrs.get("join_type"),
                    "join_condition": attrs.get("join_condition"),
                })

        for rel in row.get("entity_relations", []):
            if rel.get("name"):
                relations.append({
                    "table": rel["name"],
                    "relationship": "SHARED_ENTITY",
                    "shared_entity": rel.get("shared_entity"),
                })

        return relations

    async def search_entity_edges(
        self,
        table_name: str,
    ) -> List[Dict[str, Any]]:
        """Return all edges connected to a table (columns, joins, mappings)."""
        records = await self._execute(
            """
            MATCH (t:Table)
            WHERE t.name CONTAINS $table_name
            OPTIONAL MATCH (t)-[r]->(target)
            RETURN type(r) AS relationship,
                   target.name AS target_name,
                   labels(target) AS target_labels,
                   r.attributes AS attributes
            """,
            table_name=table_name,
        )
        return [
            {
                "relationship": r.get("relationship"),
                "target": r.get("target_name"),
                "target_labels": r.get("target_labels", []),
                "attributes": json.loads(r["attributes"]) if r.get("attributes") else {},
            }
            for r in records
            if r.get("target_name")
        ]

    # ------------------------------------------------------------------
    # query patterns
    # ------------------------------------------------------------------

    async def get_patterns_for_intent(
        self,
        intent: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return query patterns matching an intent."""
        records = await self._execute(
            """
            MATCH (p:QueryPattern {group_id: $group_id})
            WHERE p.attributes CONTAINS $intent
            RETURN p.name AS name,
                   p.summary AS summary,
                   p.attributes AS attributes
            ORDER BY p.attributes DESC
            LIMIT $top_k
            """,
            group_id=self._group_id,
            intent=intent,
            top_k=top_k,
        )
        return [
            {
                "name": r["name"],
                "summary": r.get("summary", ""),
                "attributes": json.loads(r["attributes"]) if r.get("attributes") else {},
            }
            for r in records
        ]

    async def search_patterns(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Semantic search across QueryPattern nodes."""
        embedding = await self._embed(query)
        if not embedding:
            return []

        records = await self._execute(
            """
            MATCH (p:QueryPattern {group_id: $group_id})
            WHERE p.embedding IS NOT NULL
            WITH p,
                 (2 - vec.cosineDistance(p.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            RETURN p.name AS name,
                   p.summary AS summary,
                   p.attributes AS attributes,
                   score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            group_id=self._group_id,
            embedding=embedding,
            threshold=threshold,
            top_k=top_k,
        )
        return [
            {
                "name": r["name"],
                "summary": r.get("summary", ""),
                "score": float(r.get("score", 0)),
                "attributes": json.loads(r["attributes"]) if r.get("attributes") else {},
            }
            for r in records
        ]

    # ------------------------------------------------------------------
    # stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> Dict[str, int]:
        """Count of entity nodes by label."""
        stats: Dict[str, int] = {}
        for label in NodeLabel:
            records = await self._execute(
                f"""
                MATCH (n:{label.value} {{group_id: $group_id}})
                RETURN count(n) AS cnt
                """,
                group_id=self._group_id,
            )
            stats[label.value] = records[0]["cnt"] if records else 0
        return stats

    # ------------------------------------------------------------------
    # deletion
    # ------------------------------------------------------------------

    async def delete_entity(self, uuid: str) -> bool:
        """Remove an entity and all its edges."""
        await self._execute(
            """
            MATCH (n {uuid: $uuid})
            DETACH DELETE n
            """,
            uuid=uuid,
        )
        logger.info("Deleted entity %s", uuid)
        return True

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _term_row(row: Dict) -> Dict[str, Any]:
        attrs = json.loads(row["entity_attrs"]) if row.get("entity_attrs") else {}
        return {
            "entity": row.get("entity_name"),
            "description": row.get("description", ""),
            "synonyms": attrs.get("synonyms", []),
            "mapped_tables": row.get("tables", []),
        }
