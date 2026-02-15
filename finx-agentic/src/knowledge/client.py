import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

from src.knowledge.constants import DEFAULT_GROUP_ID
from src.knowledge.models.nodes import TableNode, ColumnNode, BusinessEntityNode, DomainNode, CodeSetNode
from src.knowledge.models.edges import HasColumnEdge, EntityMappingEdge, BelongsToDomainEdge, ContainsEntityEdge, HasCodeSetEdge, ColumnMappingEdge
from src.core.cost_tracker import estimate_cost

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingCall:
    node_label: str
    node_name: str
    text_length: int
    estimated_tokens: int
    cost_usd: float
    duration_s: float


@dataclass
class GraphCostTracker:
    embedding_model: str = "text-embedding-3-large"
    calls: List[EmbeddingCall] = field(default_factory=list)

    def add(self, call: EmbeddingCall) -> None:
        self.calls.append(call)

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def total_tokens(self) -> int:
        return sum(c.estimated_tokens for c in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_duration_s(self) -> float:
        return sum(c.duration_s for c in self.calls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "embedding_model": self.embedding_model,
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_duration_s": round(self.total_duration_s, 3),
        }

    def print_summary(self) -> None:
        print("\n" + "=" * 80)
        print("GRAPH DB EMBEDDING COST SUMMARY")
        print("=" * 80)
        print(
            f"{'Label':<20} {'Node Name':<30} {'Tokens':>8} "
            f"{'Duration':>9} {'Cost ($)':>10}"
        )
        print("-" * 80)
        for c in self.calls:
            print(
                f"{c.node_label:<20} {c.node_name[:29]:<30} {c.estimated_tokens:>8,} "
                f"{c.duration_s:>8.3f}s ${c.cost_usd:>9.6f}"
            )
        print("-" * 80)
        print(
            f"{'TOTAL':<20} {f'{self.total_calls} calls':<30} {self.total_tokens:>8,} "
            f"{self.total_duration_s:>8.3f}s ${self.total_cost_usd:>9.6f}"
        )
        print("=" * 80 + "\n")


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
        self.cost_tracker = GraphCostTracker()

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

        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (n:Domain) ON (n.embedding)"
            )
            logger.info("Created vector index for Domain.embedding")
        except Exception as e:
            logger.debug(f"Vector index for Domain already exists: {e}")

        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (n:BusinessRule) ON (n.embedding)"
            )
            logger.info("Created vector index for BusinessRule.embedding")
        except Exception as e:
            logger.debug(f"Vector index for BusinessRule already exists: {e}")

        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (n:CodeSet) ON (n.embedding)"
            )
            logger.info("Created vector index for CodeSet.embedding")
        except Exception as e:
            logger.debug(f"Vector index for CodeSet already exists: {e}")

    async def load_to_graph(
        self,
        schema_path: str,
        database: Optional[str] = None,
        skip_existing: bool = False,
    ) -> Dict[str, Any]:
        schema_dir = Path(schema_path)
        
        if not schema_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {schema_path}")
        
        json_files = [f for f in schema_dir.glob("*.json") if not f.name.startswith("_")]
        
        stats = {
            "tables": 0,
            "columns": 0,
            "entities": 0,
            "edges": 0,
            "domains": 0,
            "codesets": 0,
            "skipped": 0,
        }

        self.cost_tracker = GraphCostTracker()
        
        for json_file in json_files:
            try:
                with open(json_file, "r") as f:
                    schema_data = json.load(f)

                if skip_existing:
                    table_name = schema_data["name"]
                    db = schema_data.get("database", database or "default")
                    node_name = f"{db}.{table_name}"
                    if await self._node_exists("Table", node_name):
                        logger.info(f"Skipped (exists): {node_name}")
                        stats["skipped"] += 1
                        continue
                
                file_stats = await self._load_schema(schema_data, database)
                for key in stats:
                    stats[key] += file_stats.get(key, 0)
                
                logger.info(f"Loaded schema from {json_file.name}")
            except Exception as e:
                logger.error(f"Error loading {json_file.name}: {e}")

        stats["embedding_cost"] = self.cost_tracker.to_dict()
        
        return stats

    async def _load_schema(
        self,
        schema_data: Dict,
        database: Optional[str] = None
    ) -> Dict[str, int]:
        stats = {"tables": 0, "columns": 0, "entities": 0, "edges": 0, "domains": 0, "codesets": 0}
        
        table_name = schema_data["name"]
        db = schema_data.get("database", database or "default")
        
        # --- 1. Table node ---
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
        
        # --- 2. Column nodes + HAS_COLUMN edges ---
        column_uuid_map: Dict[str, str] = {}  # col_name -> uuid
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
            column_uuid_map[col["name"]] = column_entity_saved.uuid
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

            # --- 2a. CodeSet from column "codes" field ---
            codes = col.get("codes")
            if codes and isinstance(codes, dict):
                codeset = CodeSetNode(
                    name=f"codeset_{db}_{table_name}_{col['name']}",
                    description=f"Code values for {table_name}.{col['name']}",
                    codes=codes,
                    column_name=col["name"],
                    table_name=table_name,
                    database=db,
                )
                codeset_entity = codeset.to_entity_node(self.group_id)
                codeset_saved = await self._add_node(codeset_entity)
                stats["codesets"] += 1

                cs_edge = HasCodeSetEdge(
                    column_name=col["name"],
                    table_name=table_name,
                    database=db,
                    codeset_name=codeset.name,
                )
                await self._add_edge(
                    cs_edge.to_entity_edge(
                        column_entity_saved.uuid, codeset_saved.uuid, self.group_id
                    )
                )
                stats["edges"] += 1
        
        # --- 3. BusinessEntity + ENTITY_MAPPING ---
        entity_data = schema_data.get("entity")
        business_entity_saved = None
        domain_name = None
        if entity_data:
            entity_name = entity_data.get("name", table_name.title())
            domain_name = entity_data.get("domain", "business")
            
            business_entity = BusinessEntityNode(
                name=entity_name,
                domain=domain_name,
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

            # --- 3a. Column → BusinessEntity mapping for FK columns ---
            for col in schema_data.get("columns", []):
                if col.get("foreign_key") and col["name"] in column_uuid_map:
                    col_map_edge = ColumnMappingEdge(
                        column_name=col["name"],
                        table_name=table_name,
                        database=db,
                        entity_name=entity_name,
                        confidence=0.8,
                    )
                    await self._add_edge(
                        col_map_edge.to_entity_edge(
                            column_uuid_map[col["name"]],
                            business_entity_saved.uuid,
                            self.group_id,
                        )
                    )
                    stats["edges"] += 1

        # --- 4. Domain node + BELONGS_TO_DOMAIN + CONTAINS_ENTITY ---
        if domain_name:
            domain_node = DomainNode(
                name=domain_name,
                description=f"Banking domain: {domain_name}",
            )
            domain_entity = domain_node.to_entity_node(self.group_id)
            domain_saved = await self._add_node(domain_entity)
            stats["domains"] += 1

            # Table -> Domain
            btd_edge = BelongsToDomainEdge(
                table_name=table_name,
                database=db,
                domain_name=domain_name,
            )
            await self._add_edge(
                btd_edge.to_entity_edge(
                    table_entity_saved.uuid, domain_saved.uuid, self.group_id
                )
            )
            stats["edges"] += 1

            # Domain -> BusinessEntity
            if business_entity_saved:
                ce_edge = ContainsEntityEdge(
                    domain_name=domain_name,
                    entity_name=entity_data.get("name", table_name.title()),
                )
                await self._add_edge(
                    ce_edge.to_entity_edge(
                        domain_saved.uuid, business_entity_saved.uuid, self.group_id
                    )
                )
                stats["edges"] += 1

        # --- 5. BusinessRules from "rules" field (if present) ---
        for rule_data in schema_data.get("rules", []):
            from src.knowledge.models.nodes import BusinessRuleNode
            from src.knowledge.models.edges import HasRuleEdge, AppliesToEdge

            rule_node = BusinessRuleNode(
                name=rule_data.get("name", ""),
                description=rule_data.get("description", ""),
                rule_type=rule_data.get("rule_type", "calculation"),
                expression=rule_data.get("expression", ""),
                domain=domain_name or "",
                tables_involved=[f"{db}.{table_name}"],
                columns_involved=rule_data.get("columns_involved", []),
            )
            rule_entity = rule_node.to_entity_node(self.group_id)
            rule_saved = await self._add_node(rule_entity)
            stats["entities"] += 1

            # Rule -> Table
            at_edge = AppliesToEdge(
                rule_name=rule_node.name,
                target_name=f"{db}.{table_name}",
                target_type="table",
            )
            await self._add_edge(
                at_edge.to_entity_edge(
                    rule_saved.uuid, table_entity_saved.uuid, self.group_id
                )
            )
            stats["edges"] += 1

            # Entity -> Rule
            if business_entity_saved:
                hr_edge = HasRuleEdge(
                    entity_name=entity_data.get("name", ""),
                    rule_name=rule_node.name,
                )
                await self._add_edge(
                    hr_edge.to_entity_edge(
                        business_entity_saved.uuid, rule_saved.uuid, self.group_id
                    )
                )
                stats["edges"] += 1

        return stats

    async def _node_exists(self, label: str, name: str) -> bool:
        result = await self.graphiti.driver.execute_query(
            f"MATCH (n:{label} {{name: $name}}) RETURN n.uuid LIMIT 1",
            name=name,
        )
        return bool(result and result[0])

    async def _add_node(self, node: EntityNode) -> EntityNode:
        description = (node.summary or "").replace("\n", " ").strip()
        embedding = []
        estimated_tokens = 0
        embed_duration = 0.0
        if description:
            start = time.monotonic()
            embedding = await self._embedder.create(input_data=[description])
            embed_duration = time.monotonic() - start
            estimated_tokens = max(1, len(description) // 4)
            cost = estimate_cost(
                self.cost_tracker.embedding_model, estimated_tokens, 0
            ) or 0.0
            self.cost_tracker.add(EmbeddingCall(
                node_label=node.labels[0] if node.labels else "Unknown",
                node_name=node.name,
                text_length=len(description),
                estimated_tokens=estimated_tokens,
                cost_usd=cost,
                duration_s=embed_duration,
            ))

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

