import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

from src.knowledge.models.nodes import TableNode, ColumnNode, BusinessEntityNode
from src.knowledge.models.edges import HasColumnEdge, EntityMappingEdge

logger = logging.getLogger(__name__)

DEFAULT_GROUP_ID = "finx_schema"


class GraphitiClient:

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        group_id: str = DEFAULT_GROUP_ID,
        embedder: Optional[OpenAIEmbedder] = None,
    ):
        self.host = host
        self.port = port
        self.group_id = group_id
        self._embedder = embedder
        self._graphiti: Optional[Graphiti] = None

    @property
    def graphiti(self) -> Graphiti:
        if self._graphiti is None:
            driver = FalkorDriver(host=self.host, port=self.port)
            
            if self._embedder is None:
                self._embedder = OpenAIEmbedder(
                    config=OpenAIEmbedderConfig(
                        embedding_model="text-embedding-3-large",
                        embedding_dim=3072,
                    )
                )
            
            self._graphiti = Graphiti(
                graph_driver=driver,
                embedder=self._embedder
            )
        return self._graphiti

    async def initialize(self) -> None:
        await self.graphiti.build_indices_and_constraints()
        await self._create_vector_indexes()
        logger.info("Graphiti indices and constraints initialized")

    async def _create_vector_indexes(self) -> None:
        driver = self.graphiti.driver
        
        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (n:Table) ON (n.embedding)"
            )
            logger.info("Created vector index for Table.embedding")
        except Exception as e:
            logger.debug(f"Vector index for Table already exists: {e}")
        
        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (n:Column) ON (n.embedding)"
            )
            logger.info("Created vector index for Column.embedding")
        except Exception as e:
            logger.debug(f"Vector index for Column already exists: {e}")
        
        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (n:BusinessEntity) ON (n.embedding)"
            )
            logger.info("Created vector index for BusinessEntity.embedding")
        except Exception as e:
            logger.debug(f"Vector index for BusinessEntity already exists: {e}")

    async def load_to_graph(
        self,
        schema_path: str,
        database: Optional[str] = None
    ) -> Dict[str, int]:
        schema_dir = Path(schema_path)
        
        if not schema_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {schema_path}")
        
        json_files = [f for f in schema_dir.glob("*.json") if not f.name.startswith("_")]
        
        stats = {
            "tables": 0,
            "columns": 0,
            "entities": 0,
            "edges": 0
        }
        
        for json_file in json_files:
            try:
                with open(json_file, "r") as f:
                    schema_data = json.load(f)
                
                file_stats = await self._load_schema(schema_data, database)
                stats["tables"] += file_stats["tables"]
                stats["columns"] += file_stats["columns"]
                stats["entities"] += file_stats["entities"]
                stats["edges"] += file_stats["edges"]
                
                logger.info(f"Loaded schema from {json_file.name}")
            except Exception as e:
                logger.error(f"Error loading {json_file.name}: {e}")
        
        return stats

    async def _load_schema(
        self,
        schema_data: Dict,
        database: Optional[str] = None
    ) -> Dict[str, int]:
        stats = {"tables": 0, "columns": 0, "entities": 0, "edges": 0}
        
        table_name = schema_data["name"]
        db = schema_data.get("database", database or "default")
        
        table_node = TableNode(
            name=table_name,
            database=db,
            description=schema_data.get("description", ""),
            partition_keys=schema_data.get("partition_keys", []),
            row_count=schema_data.get("row_count"),
            storage_format=schema_data.get("storage_format", ""),
            location=schema_data.get("location", "")
        )
        
        table_entity = table_node.to_entity_node(self.group_id)
        table_entity_saved = await self._add_node(table_entity)
        stats["tables"] += 1
        
        for idx, col in enumerate(schema_data.get("columns", [])):
            column_node = ColumnNode(
                name=col["name"],
                table_name=table_name,
                database=db,
                data_type=col.get("type", "string"),
                description=col.get("description", ""),
                is_primary_key=col.get("primary_key", False),
                is_foreign_key=col.get("foreign_key", False),
                is_partition=col["name"] in table_node.partition_keys,
                is_nullable=col.get("nullable", True),
                sample_values=col.get("sample_values", [])
            )
            
            column_entity = column_node.to_entity_node(self.group_id)
            column_entity_saved = await self._add_node(column_entity)
            stats["columns"] += 1
            
            has_column_edge = HasColumnEdge(
                table_name=table_name,
                database=db,
                column_name=col["name"],
                ordinal_position=idx
            )
            
            edge = has_column_edge.to_entity_edge(
                source_node_uuid=table_entity_saved.uuid,
                target_node_uuid=column_entity_saved.uuid,
                group_id=self.group_id
            )
            await self._add_edge(edge)
            stats["edges"] += 1
        
        entity_data = schema_data.get("entity")
        if entity_data:
            entity_name = entity_data.get("name", table_name.title())
            
            business_entity = BusinessEntityNode(
                name=entity_name,
                domain=entity_data.get("domain", "business"),
                description=schema_data.get("description", ""),
                synonyms=entity_data.get("synonyms", []),
                mapped_tables=[f"{db}.{table_name}"]
            )
            
            business_entity_node = business_entity.to_entity_node(self.group_id)
            business_entity_saved = await self._add_node(business_entity_node)
            stats["entities"] += 1
            
            mapping_edge = EntityMappingEdge(
                entity_name=entity_name,
                table_name=table_name,
                database=db,
                confidence=1.0,
                mapping_type="direct"
            )
            
            edge = mapping_edge.to_entity_edge(
                source_node_uuid=business_entity_saved.uuid,
                target_node_uuid=table_entity_saved.uuid,
                group_id=self.group_id
            )
            await self._add_edge(edge)
            stats["edges"] += 1
        
        return stats

    async def _add_node(self, node: EntityNode) -> EntityNode:
        description = (node.summary or "").replace("\n", " ").strip()
        embedding = []
        if description:
            embedding = await self._embedder.create(input_data=[description])

        await self.graphiti.driver.execute_query(
            f"""
            MERGE (n:{node.labels[0]} {{name: $name, group_id: $group_id}})
            SET n.uuid = $uuid,
                n.created_at = $created_at,
                n.summary = $summary,
                n.attributes = $attributes,
                n.embedding = vecf32($embedding)
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

    async def _add_edge(self, edge: EntityEdge) -> EntityEdge:
        await self.graphiti.driver.execute_query(
            f"""
            MATCH (source {{uuid: $source_uuid}})
            MATCH (target {{uuid: $target_uuid}})
            MERGE (source)-[r:{edge.name} {{source_node_uuid: $source_uuid, target_node_uuid: $target_uuid}}]->(target)
            SET r.uuid = $uuid,
                r.group_id = $group_id,
                r.created_at = $created_at,
                r.fact = $fact,
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
        
        return edge

    async def close(self) -> None:
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    async def ping(self) -> bool:
        try:
            await self.graphiti.build_indices_and_constraints()
            return True
        except Exception:
            return False


_client_instance: Optional[GraphitiClient] = None


def get_graphiti_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    group_id: str = DEFAULT_GROUP_ID,
) -> GraphitiClient:
    global _client_instance
    if _client_instance is None:
        resolved_host = host or os.getenv("FALKORDB_HOST", "localhost")
        resolved_port = port or int(os.getenv("FALKORDB_PORT", "6379"))
        _client_instance = GraphitiClient(
            host=resolved_host,
            port=resolved_port,
            group_id=group_id,
        )
    return _client_instance

