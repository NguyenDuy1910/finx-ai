"""SchemaIndexer — reads JSON schema files and loads them into the graph."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph.schemas.nodes import (
    BusinessEntityNode,
    BusinessRuleNode,
    CodeSetNode,
    ColumnNode,
    DomainNode,
    TableNode,
)
from src.knowledge.graph.schemas.edges import (
    AppliesToEdge,
    BelongsToDomainEdge,
    ColumnMappingEdge,
    ContainsEntityEdge,
    EntityMappingEdge,
    HasCodeSetEdge,
    HasColumnEdge,
    HasRuleEdge,
)

logger = logging.getLogger(__name__)


class SchemaIndexer:
    """Load JSON schema files into the knowledge graph."""

    def __init__(self, client: GraphitiClient):
        self._client = client

    async def load_directory(
        self,
        schema_path: str,
        database: Optional[str] = None,
        skip_existing: bool = False,
    ) -> Dict[str, Any]:
        """Load all ``*.json`` files in *schema_path*."""
        schema_dir = Path(schema_path)
        if not schema_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {schema_path}")

        json_files = [f for f in schema_dir.glob("*.json") if not f.name.startswith("_")]

        stats: Dict[str, int] = {
            "tables": 0, "columns": 0, "entities": 0,
            "edges": 0, "domains": 0, "codesets": 0, "skipped": 0,
        }

        self._client.cost_tracker.calls.clear()

        for json_file in json_files:
            try:
                with open(json_file, "r") as f:
                    schema_data = json.load(f)

                if skip_existing:
                    table_name = schema_data["name"]
                    db = schema_data.get("database", database or "default")
                    node_name = f"{db}.{table_name}"
                    if await self._client._node_exists("Table", node_name):
                        stats["skipped"] += 1
                        continue

                file_stats = await self._load_schema(schema_data, database)
                for key in stats:
                    stats[key] += file_stats.get(key, 0)
            except Exception as e:
                logger.error("Error loading %s: %s", json_file.name, e)

        stats["embedding_cost"] = self._client.cost_tracker.to_dict()  # type: ignore[assignment]
        return stats

    async def _load_schema(
        self,
        schema_data: Dict,
        database: Optional[str] = None,
    ) -> Dict[str, int]:
        stats = {
            "tables": 0, "columns": 0, "entities": 0,
            "edges": 0, "domains": 0, "codesets": 0,
        }
        group_id = self._client.group_id

        table_name = schema_data["name"]
        db = schema_data.get("database", database or "default")

        # 1. Table node
        table_node = TableNode(
            name=table_name, database=db,
            description=schema_data.get("description", ""),
            partition_keys=schema_data.get("partition_keys", []),
            row_count=schema_data.get("row_count"),
            storage_format=schema_data.get("storage_format", ""),
            location=schema_data.get("location", ""),
        )
        table_entity = await self._client.add_node(table_node.to_entity_node(group_id))
        stats["tables"] += 1

        # 2. Column nodes + HAS_COLUMN edges
        column_uuid_map: Dict[str, str] = {}
        for idx, col in enumerate(schema_data.get("columns", [])):
            column_node = ColumnNode(
                name=col["name"], table_name=table_name, database=db,
                data_type=col.get("type", "string"),
                description=col.get("description", ""),
                is_primary_key=col.get("primary_key", False),
                is_foreign_key=col.get("foreign_key", False),
                is_partition=col["name"] in table_node.partition_keys,
                is_nullable=col.get("nullable", True),
                sample_values=col.get("sample_values", []),
            )
            col_entity = await self._client.add_node(column_node.to_entity_node(group_id))
            column_uuid_map[col["name"]] = col_entity.uuid
            stats["columns"] += 1

            edge = HasColumnEdge(
                table_name=table_name, database=db,
                column_name=col["name"], ordinal_position=idx,
            )
            await self._client.add_edge(
                edge.to_entity_edge(table_entity.uuid, col_entity.uuid, group_id)
            )
            stats["edges"] += 1

            # CodeSet for coded columns
            codes = col.get("codes")
            if codes and isinstance(codes, dict):
                codeset = CodeSetNode(
                    name=f"codeset_{db}_{table_name}_{col['name']}",
                    description=f"Code values for {table_name}.{col['name']}",
                    codes=codes, column_name=col["name"],
                    table_name=table_name, database=db,
                )
                cs_entity = await self._client.add_node(codeset.to_entity_node(group_id))
                stats["codesets"] += 1

                cs_edge = HasCodeSetEdge(
                    column_name=col["name"], table_name=table_name,
                    database=db, codeset_name=codeset.name,
                )
                await self._client.add_edge(
                    cs_edge.to_entity_edge(col_entity.uuid, cs_entity.uuid, group_id)
                )
                stats["edges"] += 1

        # 3. BusinessEntity + ENTITY_MAPPING
        entity_data = schema_data.get("entity")
        business_entity_saved = None
        domain_name = None

        if entity_data:
            entity_name = entity_data.get("name", table_name.title())
            domain_name = entity_data.get("domain", "business")

            be_node = BusinessEntityNode(
                name=entity_name, domain=domain_name,
                description=schema_data.get("description", ""),
                synonyms=entity_data.get("synonyms", []),
                mapped_tables=[f"{db}.{table_name}"],
            )
            business_entity_saved = await self._client.add_node(be_node.to_entity_node(group_id))
            stats["entities"] += 1

            mapping_edge = EntityMappingEdge(
                entity_name=entity_name, table_name=table_name,
                database=db, confidence=1.0, mapping_type="direct",
            )
            await self._client.add_edge(
                mapping_edge.to_entity_edge(
                    business_entity_saved.uuid, table_entity.uuid, group_id,
                )
            )
            stats["edges"] += 1

            # Column → BusinessEntity mapping for FK columns
            for col in schema_data.get("columns", []):
                if col.get("foreign_key") and col["name"] in column_uuid_map:
                    col_map = ColumnMappingEdge(
                        column_name=col["name"], table_name=table_name,
                        database=db, entity_name=entity_name, confidence=0.8,
                    )
                    await self._client.add_edge(
                        col_map.to_entity_edge(
                            column_uuid_map[col["name"]],
                            business_entity_saved.uuid,
                            group_id,
                        )
                    )
                    stats["edges"] += 1

        # 4. Domain node + edges
        if domain_name:
            domain_node = DomainNode(
                name=domain_name,
                description=f"Banking domain: {domain_name}",
            )
            domain_saved = await self._client.add_node(domain_node.to_entity_node(group_id))
            stats["domains"] += 1

            btd_edge = BelongsToDomainEdge(
                table_name=table_name, database=db, domain_name=domain_name,
            )
            await self._client.add_edge(
                btd_edge.to_entity_edge(table_entity.uuid, domain_saved.uuid, group_id)
            )
            stats["edges"] += 1

            if business_entity_saved:
                ce_edge = ContainsEntityEdge(
                    domain_name=domain_name,
                    entity_name=entity_data.get("name", table_name.title()),
                )
                await self._client.add_edge(
                    ce_edge.to_entity_edge(
                        domain_saved.uuid, business_entity_saved.uuid, group_id,
                    )
                )
                stats["edges"] += 1

        # 5. BusinessRules
        for rule_data in schema_data.get("rules", []):
            rule_node = BusinessRuleNode(
                name=rule_data.get("name", ""),
                description=rule_data.get("description", ""),
                rule_type=rule_data.get("rule_type", "calculation"),
                expression=rule_data.get("expression", ""),
                domain=domain_name or "",
                tables_involved=[f"{db}.{table_name}"],
                columns_involved=rule_data.get("columns_involved", []),
            )
            rule_saved = await self._client.add_node(rule_node.to_entity_node(group_id))
            stats["entities"] += 1

            at_edge = AppliesToEdge(
                rule_name=rule_node.name,
                target_name=f"{db}.{table_name}",
                target_type="table",
            )
            await self._client.add_edge(
                at_edge.to_entity_edge(rule_saved.uuid, table_entity.uuid, group_id)
            )
            stats["edges"] += 1

            if business_entity_saved:
                hr_edge = HasRuleEdge(
                    entity_name=entity_data.get("name", ""),
                    rule_name=rule_node.name,
                )
                await self._client.add_edge(
                    hr_edge.to_entity_edge(
                        business_entity_saved.uuid, rule_saved.uuid, group_id,
                    )
                )
                stats["edges"] += 1

        return stats
