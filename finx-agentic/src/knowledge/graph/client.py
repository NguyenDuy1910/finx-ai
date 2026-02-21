import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

from src.knowledge.constants import DEFAULT_GROUP_ID
from src.knowledge.graph.cost_tracker import GraphCostTracker, EmbeddingCall
from src.core.cost_tracker import estimate_cost

logger = logging.getLogger(__name__)


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
            self._graphiti = Graphiti(graph_driver=driver, embedder=self._embedder)
        return self._graphiti

    async def initialize(self) -> None:
        await self.graphiti.build_indices_and_constraints()
        await self._create_vector_indexes()

    _VECTOR_LABELS = [
        "Table", "Column", "BusinessEntity", "Domain", "BusinessRule", "CodeSet",
    ]
    _EMBEDDING_DIM = 3072

    async def _create_vector_indexes(self) -> None:
        driver = self.graphiti.driver
        for label in self._VECTOR_LABELS:
            try:
                await driver.execute_query(f"DROP INDEX ON :{label}(embedding)")
            except Exception:
                pass
            try:
                await driver.execute_query(
                    f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.embedding) "
                    f"OPTIONS {{dimension: {self._EMBEDDING_DIM}, similarityFunction: 'cosine'}}"
                )
            except Exception:
                pass

    async def add_node(self, node: EntityNode) -> EntityNode:
        description = (node.summary or "").replace("\n", " ").strip()
        embedding: List[float] = []
        if description:
            start = time.monotonic()
            embedding = await self._embedder.create(input_data=[description])
            embed_duration = time.monotonic() - start
            estimated_tokens = max(1, len(description) // 4)
            cost = estimate_cost(
                self.cost_tracker.embedding_model, estimated_tokens, 0,
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

    async def add_edge(self, edge: EntityEdge) -> EntityEdge:
        await self.graphiti.driver.execute_query(
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
