import json
import logging
from typing import Dict, List, Any, Optional

from src.knowledge.client import GraphitiClient
from src.knowledge.models.nodes import TableNode, ColumnNode, BusinessEntityNode, DomainNode
from src.knowledge.models.edges import HasColumnEdge, EntityMappingEdge, BelongsToDomainEdge, ContainsEntityEdge

logger = logging.getLogger(__name__)


class GraphUpdater:

    def __init__(self, client: GraphitiClient):
        self.client = client

    async def add_table(self, schema_data: Dict[str, Any]) -> Dict[str, int]:
        return await self.client._load_schema(schema_data)

    async def remove_table(self, table_name: str, database: str) -> Dict[str, int]:
        stats = {"removed_nodes": 0, "removed_edges": 0}
        node_name = f"{database}.{table_name}"

        result = await self.client.graphiti.driver.execute_query(
            """
            MATCH (t:Table {name: $name})
            OPTIONAL MATCH (t)-[r1:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (c)-[r2]-()
            RETURN collect(DISTINCT id(c)) as col_ids,
                   collect(DISTINCT id(r1)) as edge1_ids,
                   collect(DISTINCT id(r2)) as edge2_ids
            """,
            name=node_name,
        )

        await self.client.graphiti.driver.execute_query(
            """
            MATCH (t:Table {name: $name})
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (c)-[cr]-()
            DELETE cr
            """,
            name=node_name,
        )

        await self.client.graphiti.driver.execute_query(
            """
            MATCH (t:Table {name: $name})
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            DETACH DELETE c
            """,
            name=node_name,
        )

        await self.client.graphiti.driver.execute_query(
            """
            MATCH (t:Table {name: $name})
            DETACH DELETE t
            """,
            name=node_name,
        )

        logger.info(f"Removed table node and related nodes: {node_name}")
        stats["removed_nodes"] += 1
        return stats

    async def add_columns(
        self,
        table_name: str,
        database: str,
        columns: List[Dict[str, Any]],
        start_ordinal: int = 0,
    ) -> Dict[str, int]:
        stats = {"columns": 0, "edges": 0}
        node_name = f"{database}.{table_name}"

        table_result = await self.client.graphiti.driver.execute_query(
            "MATCH (t:Table {name: $name}) RETURN t.uuid as uuid",
            name=node_name,
        )

        if not table_result or not table_result[0]:
            logger.warning(f"Table node not found: {node_name}")
            return stats

        table_uuid = table_result[0][0]["uuid"]

        for idx, col in enumerate(columns):
            column_node = ColumnNode(
                name=col["name"],
                table_name=table_name,
                database=database,
                data_type=col.get("type", "string"),
                description=col.get("description", ""),
                is_primary_key=col.get("primary_key", False),
                is_foreign_key=col.get("foreign_key", False),
                is_partition=False,
                is_nullable=col.get("nullable", True),
                sample_values=col.get("sample_values", []),
            )

            column_entity = column_node.to_entity_node(self.client.group_id)
            column_saved = await self.client._add_node(column_entity)
            stats["columns"] += 1

            has_column_edge = HasColumnEdge(
                table_name=table_name,
                database=database,
                column_name=col["name"],
                ordinal_position=start_ordinal + idx,
            )
            edge = has_column_edge.to_entity_edge(
                source_node_uuid=table_uuid,
                target_node_uuid=column_saved.uuid,
                group_id=self.client.group_id,
            )
            await self.client._add_edge(edge)
            stats["edges"] += 1

        logger.info(f"Added {stats['columns']} columns to {node_name}")
        return stats

    async def remove_columns(
        self,
        table_name: str,
        database: str,
        column_names: List[str],
    ) -> Dict[str, int]:
        stats = {"removed_columns": 0}

        for col_name in column_names:
            node_name = f"{database}.{table_name}.{col_name}"
            await self.client.graphiti.driver.execute_query(
                """
                MATCH (c:Column {name: $name})
                DETACH DELETE c
                """,
                name=node_name,
            )
            stats["removed_columns"] += 1
            logger.info(f"Removed column node: {node_name}")

        return stats

    async def update_column_type(
        self,
        table_name: str,
        database: str,
        col_name: str,
        new_type: str,
    ) -> None:
        node_name = f"{database}.{table_name}.{col_name}"

        result = await self.client.graphiti.driver.execute_query(
            "MATCH (c:Column {name: $name}) RETURN c.attributes as attrs",
            name=node_name,
        )

        if not result or not result[0]:
            logger.warning(f"Column node not found: {node_name}")
            return

        attrs = json.loads(result[0][0]["attrs"]) if isinstance(result[0][0]["attrs"], str) else result[0][0]["attrs"]
        attrs["data_type"] = new_type

        await self.client.graphiti.driver.execute_query(
            """
            MATCH (c:Column {name: $name})
            SET c.attributes = $attributes
            """,
            name=node_name,
            attributes=json.dumps(attrs),
        )
        logger.info(f"Updated column type: {node_name} -> {new_type}")
