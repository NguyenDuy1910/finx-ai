"""EntityIndexer — register (upsert) entity nodes and edges into the graph."""

import json
import logging
from typing import Any, Dict, List, Optional

from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph.schemas.enums import NodeLabel
from src.knowledge.graph.schemas.nodes import (
    BusinessEntityNode,
    BusinessRuleNode,
    CodeSetNode,
    ColumnNode,
    DomainNode,
    QueryPatternNode,
    TableNode,
)
from src.knowledge.graph.schemas.edges import (
    AppliesToEdge,
    BelongsToDomainEdge,
    ColumnMappingEdge,
    ContainsEntityEdge,
    DerivedFromEdge,
    EntityMappingEdge,
    ForeignKeyEdge,
    HasCodeSetEdge,
    HasColumnEdge,
    HasRuleEdge,
    JoinEdge,
    QueryPatternEdge,
    SynonymEdge,
)

logger = logging.getLogger(__name__)


class EntityIndexer:
    """Upsert entity nodes and relationship edges into the graph."""

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

    # ── register nodes ───────────────────────────────────────────────

    async def register_table(self, table: TableNode) -> EntityNode:
        return await self._upsert_entity(table.to_entity_node(self._group_id), NodeLabel.TABLE)

    async def register_column(self, column: ColumnNode) -> EntityNode:
        return await self._upsert_entity(column.to_entity_node(self._group_id), NodeLabel.COLUMN)

    async def register_business_entity(self, entity_model: BusinessEntityNode) -> EntityNode:
        return await self._upsert_entity(entity_model.to_entity_node(self._group_id), NodeLabel.BUSINESS_ENTITY)

    async def register_query_pattern(self, pattern: QueryPatternNode) -> EntityNode:
        return await self._upsert_entity(pattern.to_entity_node(self._group_id), NodeLabel.QUERY_PATTERN)

    async def register_domain(self, domain: DomainNode) -> EntityNode:
        return await self._upsert_entity(domain.to_entity_node(self._group_id), NodeLabel.DOMAIN)

    async def register_business_rule(self, rule: BusinessRuleNode) -> EntityNode:
        return await self._upsert_entity(rule.to_entity_node(self._group_id), NodeLabel.BUSINESS_RULE)

    async def register_codeset(self, codeset: CodeSetNode) -> EntityNode:
        return await self._upsert_entity(codeset.to_entity_node(self._group_id), NodeLabel.CODE_SET)

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
        return node

    # ── register edges ───────────────────────────────────────────────

    async def register_has_column(self, edge: HasColumnEdge, table_uuid: str, column_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(table_uuid, column_uuid, self._group_id))

    async def register_join(self, edge: JoinEdge, source_uuid: str, target_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(source_uuid, target_uuid, self._group_id))

    async def register_entity_mapping(self, edge: EntityMappingEdge, entity_uuid: str, table_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(entity_uuid, table_uuid, self._group_id))

    async def register_foreign_key(self, edge: ForeignKeyEdge, source_uuid: str, target_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(source_uuid, target_uuid, self._group_id))

    async def register_synonym(self, edge: SynonymEdge, source_uuid: str, target_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(source_uuid, target_uuid, self._group_id))

    async def register_query_pattern_edge(self, edge: QueryPatternEdge, pattern_uuid: str, table_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(pattern_uuid, table_uuid, self._group_id))

    async def register_belongs_to_domain(self, edge: BelongsToDomainEdge, table_uuid: str, domain_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(table_uuid, domain_uuid, self._group_id))

    async def register_contains_entity(self, edge: ContainsEntityEdge, domain_uuid: str, entity_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(domain_uuid, entity_uuid, self._group_id))

    async def register_has_rule(self, edge: HasRuleEdge, entity_uuid: str, rule_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(entity_uuid, rule_uuid, self._group_id))

    async def register_applies_to(self, edge: AppliesToEdge, rule_uuid: str, target_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(rule_uuid, target_uuid, self._group_id))

    async def register_column_mapping(self, edge: ColumnMappingEdge, column_uuid: str, entity_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(column_uuid, entity_uuid, self._group_id))

    async def register_has_codeset(self, edge: HasCodeSetEdge, column_uuid: str, codeset_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(column_uuid, codeset_uuid, self._group_id))

    async def register_derived_from(self, edge: DerivedFromEdge, source_uuid: str, target_uuid: str) -> None:
        await self._upsert_edge(edge.to_entity_edge(source_uuid, target_uuid, self._group_id))

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

    # ── deletion ─────────────────────────────────────────────────────

    async def delete_entity(self, uuid: str) -> bool:
        await self._execute("MATCH (n {uuid: $uuid}) DETACH DELETE n", uuid=uuid)
        return True
