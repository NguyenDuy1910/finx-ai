"""EntityQueries — read-only lookups, traversals, searches, stats over the graph."""

import json
import logging
from typing import Any, Dict, List, Optional

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph.schemas.enums import NodeLabel

logger = logging.getLogger(__name__)


class EntityQueries:
    """Read-only queries against entity / edge nodes."""

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

    @staticmethod
    def _parse_row(row: Dict) -> Dict[str, Any]:
        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "summary": row.get("summary", ""),
            "attributes": json.loads(row["attributes"]) if row.get("attributes") else {},
        }

    # ── table lookups ────────────────────────────────────────────────

    async def get_table(self, table_name: str, database: Optional[str] = None) -> Optional[Dict]:
        name = f"{database}.{table_name}" if database else table_name
        records = await self._execute(
            """
            MATCH (t:Table)
            WHERE t.name = $name OR t.name CONTAINS $table_name
            RETURN t.uuid AS uuid, t.name AS name, t.summary AS summary, t.attributes AS attributes
            LIMIT 1
            """,
            name=name, table_name=table_name,
        )
        return self._parse_row(records[0]) if records else None

    async def get_all_tables(self, database: Optional[str] = None, offset: int = 0, limit: int = 50) -> List[Dict]:
        if database:
            records = await self._execute(
                """
                MATCH (t:Table) WHERE t.name STARTS WITH $prefix
                RETURN t.uuid AS uuid, t.name AS name, t.summary AS summary, t.attributes AS attributes
                ORDER BY t.name SKIP $offset LIMIT $limit
                """,
                prefix=f"{database}.", offset=offset, limit=limit,
            )
        else:
            records = await self._execute(
                """
                MATCH (t:Table)
                RETURN t.uuid AS uuid, t.name AS name, t.summary AS summary, t.attributes AS attributes
                ORDER BY t.name SKIP $offset LIMIT $limit
                """,
                offset=offset, limit=limit,
            )
        return [self._parse_row(r) for r in records]

    async def get_columns_for_table(self, table_name: str, database: Optional[str] = None) -> List[Dict]:
        full_name = f"{database}.{table_name}" if database else table_name
        records = await self._execute(
            """
            MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
            WHERE t.name = $name OR t.name CONTAINS $table_name
            RETURN c.uuid AS uuid, c.name AS name, c.summary AS summary, c.attributes AS attributes
            """,
            name=full_name, table_name=table_name,
        )
        return [self._parse_row(r) for r in records]

    # ── entity lookups ───────────────────────────────────────────────

    async def get_all_entities(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (e:BusinessEntity)
            RETURN e.uuid AS uuid, e.name AS name, e.summary AS summary, e.attributes AS attributes
            ORDER BY e.name SKIP $offset LIMIT $limit
            """,
            offset=offset, limit=limit,
        )
        return [self._parse_row(r) for r in records]

    # ── pattern lookups ──────────────────────────────────────────────

    async def get_all_patterns(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (p:QueryPattern)
            RETURN p.uuid AS uuid, p.name AS name, p.summary AS summary, p.attributes AS attributes
            ORDER BY p.name SKIP $offset LIMIT $limit
            """,
            offset=offset, limit=limit,
        )
        return [self._parse_row(r) for r in records]

    async def get_patterns_for_intent(self, intent: str, top_k: int = 5) -> List[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (p:QueryPattern {group_id: $group_id})
            WHERE p.attributes CONTAINS $intent
            RETURN p.name AS name, p.summary AS summary, p.attributes AS attributes
            ORDER BY p.attributes DESC LIMIT $top_k
            """,
            group_id=self._group_id, intent=intent, top_k=top_k,
        )
        return [
            {"name": r["name"], "summary": r.get("summary", ""),
             "attributes": json.loads(r["attributes"]) if r.get("attributes") else {}}
            for r in records
        ]

    async def search_patterns(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[Dict[str, Any]]:
        embedding = await self._embed(query)
        if not embedding:
            return []
        records = await self._execute(
            """
            MATCH (p:QueryPattern {group_id: $group_id})
            WHERE p.embedding IS NOT NULL
            WITH p, (2 - vec.cosineDistance(p.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            RETURN p.name AS name, p.summary AS summary, p.attributes AS attributes, score
            ORDER BY score DESC LIMIT $top_k
            """,
            group_id=self._group_id, embedding=embedding, threshold=threshold, top_k=top_k,
        )
        return [
            {"name": r["name"], "summary": r.get("summary", ""), "score": float(r.get("score", 0)),
             "attributes": json.loads(r["attributes"]) if r.get("attributes") else {}}
            for r in records
        ]

    # ── domain lookups ───────────────────────────────────────────────

    async def get_all_domains(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (d:Domain)
            RETURN d.uuid AS uuid, d.name AS name, d.summary AS summary, d.attributes AS attributes
            ORDER BY d.name SKIP $offset LIMIT $limit
            """,
            offset=offset, limit=limit,
        )
        return [self._parse_row(r) for r in records]

    async def get_domain(self, domain_name: str) -> Optional[Dict]:
        records = await self._execute(
            """
            MATCH (d:Domain) WHERE toLower(d.name) = toLower($name)
            OPTIONAL MATCH (t:Table)-[:BELONGS_TO_DOMAIN]->(d)
            OPTIONAL MATCH (d)-[:CONTAINS_ENTITY]->(e:BusinessEntity)
            RETURN d.uuid AS uuid, d.name AS name, d.summary AS summary,
                   d.attributes AS attributes,
                   collect(DISTINCT t.name) AS tables,
                   collect(DISTINCT e.name) AS entities
            """,
            name=domain_name,
        )
        if not records:
            return None
        row = records[0]
        return {
            **self._parse_row(row),
            "tables": row.get("tables", []),
            "entities": row.get("entities", []),
        }

    async def get_tables_by_domain(self, domain_name: str) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (t:Table)-[:BELONGS_TO_DOMAIN]->(d:Domain)
            WHERE toLower(d.name) = toLower($domain_name)
            RETURN t.uuid AS uuid, t.name AS name, t.summary AS summary, t.attributes AS attributes
            ORDER BY t.name
            """,
            domain_name=domain_name,
        )
        return [self._parse_row(r) for r in records]

    # ── rule lookups ─────────────────────────────────────────────────

    async def get_all_rules(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (r:BusinessRule)
            RETURN r.uuid AS uuid, r.name AS name, r.summary AS summary, r.attributes AS attributes
            ORDER BY r.name SKIP $offset LIMIT $limit
            """,
            offset=offset, limit=limit,
        )
        return [self._parse_row(r) for r in records]

    async def get_rules_for_table(self, table_name: str) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (rule:BusinessRule)-[:APPLIES_TO]->(t:Table)
            WHERE t.name CONTAINS $table_name
            RETURN rule.uuid AS uuid, rule.name AS name, rule.summary AS summary, rule.attributes AS attributes
            ORDER BY rule.name
            """,
            table_name=table_name,
        )
        return [self._parse_row(r) for r in records]

    async def get_rules_for_entity(self, entity_name: str) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (e:BusinessEntity)-[:HAS_RULE]->(rule:BusinessRule)
            WHERE toLower(e.name) = toLower($entity_name)
            RETURN rule.uuid AS uuid, rule.name AS name, rule.summary AS summary, rule.attributes AS attributes
            ORDER BY rule.name
            """,
            entity_name=entity_name,
        )
        return [self._parse_row(r) for r in records]

    # ── codeset lookups ──────────────────────────────────────────────

    async def get_codeset_for_column(self, table_name: str, column_name: str) -> Optional[Dict]:
        records = await self._execute(
            """
            MATCH (c:Column)-[:HAS_CODESET]->(cs:CodeSet)
            WHERE c.name CONTAINS $column_name AND c.name CONTAINS $table_name
            RETURN cs.uuid AS uuid, cs.name AS name, cs.summary AS summary, cs.attributes AS attributes
            LIMIT 1
            """,
            table_name=table_name, column_name=column_name,
        )
        return self._parse_row(records[0]) if records else None

    async def get_all_codesets(self, offset: int = 0, limit: int = 50) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (cs:CodeSet)
            RETURN cs.uuid AS uuid, cs.name AS name, cs.summary AS summary, cs.attributes AS attributes
            ORDER BY cs.name SKIP $offset LIMIT $limit
            """,
            offset=offset, limit=limit,
        )
        return [self._parse_row(r) for r in records]

    # ── business-term resolution ─────────────────────────────────────

    async def resolve_term(self, term: str) -> List[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (e:BusinessEntity)
            WHERE toLower(e.name) = toLower($term) OR e.attributes CONTAINS $term
            OPTIONAL MATCH (e)-[:ENTITY_MAPPING]->(t:Table)
            RETURN e.name AS entity_name, e.summary AS description,
                   e.attributes AS entity_attrs, collect(DISTINCT t.name) AS tables
            """,
            term=term,
        )
        if records and records[0].get("entity_name"):
            return [self._term_row(r) for r in records]
        return await self.search_entities(term)

    async def search_entities(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[Dict[str, Any]]:
        embedding = await self._embed(query)
        if not embedding:
            return []
        records = await self._execute(
            """
            MATCH (e:BusinessEntity {group_id: $group_id})
            WHERE e.embedding IS NOT NULL
            WITH e, (2 - vec.cosineDistance(e.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            OPTIONAL MATCH (e)-[:ENTITY_MAPPING]->(t:Table)
            RETURN e.name AS entity_name, e.summary AS description,
                   e.attributes AS entity_attrs, collect(DISTINCT t.name) AS tables, score
            ORDER BY score DESC LIMIT $top_k
            """,
            group_id=self._group_id, embedding=embedding, threshold=threshold, top_k=top_k,
        )
        return [{**self._term_row(r), "score": float(r.get("score", 0))} for r in records]

    # ── relationship traversal ───────────────────────────────────────

    async def find_related_tables(self, table_name: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
        full_name = f"{database}.{table_name}" if database else table_name
        records = await self._execute(
            """
            MATCH (t:Table) WHERE t.name = $name OR t.name CONTAINS $table_name
            OPTIONAL MATCH (t)-[r:JOIN|FOREIGN_KEY]-(related:Table)
            OPTIONAL MATCH (e:BusinessEntity)-[:ENTITY_MAPPING]->(t)
            OPTIONAL MATCH (e)-[:ENTITY_MAPPING]->(sibling:Table) WHERE sibling <> t
            RETURN t.name AS source,
                   collect(DISTINCT {name: related.name, relationship: type(r), attributes: r.attributes}) AS direct_relations,
                   collect(DISTINCT {name: sibling.name, shared_entity: e.name}) AS entity_relations
            """,
            name=full_name, table_name=table_name,
        )
        if not records:
            return []
        row = records[0]
        relations: List[Dict[str, Any]] = []
        for rel in row.get("direct_relations", []):
            if rel.get("name"):
                attrs = json.loads(rel["attributes"]) if rel.get("attributes") else {}
                relations.append({
                    "table": rel["name"], "relationship": rel.get("relationship", "RELATED"),
                    "join_type": attrs.get("join_type"), "join_condition": attrs.get("join_condition"),
                })
        for rel in row.get("entity_relations", []):
            if rel.get("name"):
                relations.append({
                    "table": rel["name"], "relationship": "SHARED_ENTITY",
                    "shared_entity": rel.get("shared_entity"),
                })
        return relations

    async def search_entity_edges(self, table_name: str) -> List[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (t:Table) WHERE t.name CONTAINS $table_name
            OPTIONAL MATCH (t)-[r]->(target)
            RETURN type(r) AS relationship, target.name AS target_name,
                   labels(target) AS target_labels, r.attributes AS attributes
            """,
            table_name=table_name,
        )
        return [
            {"relationship": r.get("relationship"), "target": r.get("target_name"),
             "target_labels": r.get("target_labels", []),
             "attributes": json.loads(r["attributes"]) if r.get("attributes") else {}}
            for r in records if r.get("target_name")
        ]

    # ── lineage ──────────────────────────────────────────────────────

    async def get_entity_for_column(self, table_name: str, column_name: str) -> Optional[Dict]:
        records = await self._execute(
            """
            MATCH (c:Column)-[:COLUMN_MAPPING]->(e:BusinessEntity)
            WHERE c.name CONTAINS $column_name AND c.name CONTAINS $table_name
            RETURN e.uuid AS uuid, e.name AS name, e.summary AS summary, e.attributes AS attributes
            LIMIT 1
            """,
            table_name=table_name, column_name=column_name,
        )
        return self._parse_row(records[0]) if records else None

    async def get_column_lineage(self, table_name: str, column_name: str) -> List[Dict]:
        records = await self._execute(
            """
            MATCH (c:Column)-[:DERIVED_FROM*1..3]->(source:Column)
            WHERE c.name CONTAINS $column_name AND c.name CONTAINS $table_name
            RETURN source.name AS name, source.summary AS summary, source.attributes AS attributes
            """,
            table_name=table_name, column_name=column_name,
        )
        return [
            {"name": r["name"], "summary": r.get("summary", ""),
             "attributes": json.loads(r["attributes"]) if r.get("attributes") else {}}
            for r in records
        ]

    # ── stats ────────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for label in NodeLabel:
            records = await self._execute(
                f"MATCH (n:{label.value} {{group_id: $group_id}}) RETURN count(n) AS cnt",
                group_id=self._group_id,
            )
            stats[label.value] = records[0]["cnt"] if records else 0
        return stats

    @staticmethod
    def _term_row(row: Dict) -> Dict[str, Any]:
        attrs = json.loads(row["entity_attrs"]) if row.get("entity_attrs") else {}
        return {
            "entity": row.get("entity_name"),
            "description": row.get("description", ""),
            "synonyms": attrs.get("synonyms", []),
            "mapped_tables": row.get("tables", []),
        }
