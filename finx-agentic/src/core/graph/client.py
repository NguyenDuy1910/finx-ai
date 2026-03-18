"""GraphitiClient — thin wrapper over graphiti_core.Graphiti with FalkorDB."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMConfig, OpenAIClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_config import SearchConfig, SearchResults
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF
from graphiti_core.search.search_filters import SearchFilters
from graphiti_core.utils.bulk_utils import RawEpisode
from pydantic import BaseModel

from src.core.llm_cost_tracker import LLMCostTracker, wrap_openai_client
from src.core.graph.ontology import EDGE_TYPES, EDGE_TYPE_MAP, ENTITY_TYPES
from src.core.graph.ontology.extraction_config import build_extraction_instructions

logger = logging.getLogger(__name__)

GROUP_ID = "finx_knowledge"
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_SMALL_MODEL = "gpt-4.1-nano"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_EMBEDDING_DIM = 3072


def _attach_cost_tracking(obj: Any, *, tracker: LLMCostTracker) -> None:
    if hasattr(obj, "client"):
        obj.client = wrap_openai_client(obj.client, tracker=tracker)


class GraphitiClient:
    """Thin async wrapper around graphiti_core.Graphiti.

    Manages FalkorDB connection, LLM clients, embeddings, and cost tracking.
    Use ``get_graphiti_client()`` for the app-wide singleton.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 6379,
        group_id: str = GROUP_ID,
        llm_model: Optional[str] = None,
        small_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        embedding_dim: Optional[int] = None,
        llm_client: Optional[OpenAIClient] = None,
        embedder: Optional[OpenAIEmbedder] = None,
        cross_encoder: Optional[OpenAIRerankerClient] = None,
    ):
        self.host = host
        self.port = port
        self.group_id = group_id
        self._llm_model = llm_model or os.getenv("GRAPHITI_LLM_MODEL", DEFAULT_LLM_MODEL)
        self._small_model = small_model or os.getenv("GRAPHITI_SMALL_MODEL", DEFAULT_SMALL_MODEL)
        self._embedding_model = embedding_model or os.getenv(
            "GRAPHITI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )
        self._embedding_dim = embedding_dim or int(
            os.getenv("GRAPHITI_EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM))
        )
        self._llm_client = llm_client
        self._embedder = embedder
        self._cross_encoder = cross_encoder
        self._graphiti: Optional[Graphiti] = None
        self.cost_tracker = LLMCostTracker()

    # ── lazy init ────────────────────────────────────────────────────────────

    @property
    def graphiti(self) -> Graphiti:
        if self._graphiti is None:
            driver = FalkorDriver(host=self.host, port=self.port)
            llm_config = LLMConfig(model=self._llm_model, small_model=self._small_model)
            if self._llm_client is None:
                self._llm_client = OpenAIClient(config=llm_config)
            _attach_cost_tracking(self._llm_client, tracker=self.cost_tracker)
            if self._embedder is None:
                self._embedder = OpenAIEmbedder(
                    config=OpenAIEmbedderConfig(
                        embedding_model=self._embedding_model,
                        embedding_dim=self._embedding_dim,
                    )
                )
            _attach_cost_tracking(self._embedder, tracker=self.cost_tracker)
            if self._cross_encoder is None:
                self._cross_encoder = OpenAIRerankerClient(
                    config=LLMConfig(model=self._small_model),
                )
            _attach_cost_tracking(self._cross_encoder, tracker=self.cost_tracker)
            self._graphiti = Graphiti(
                graph_driver=driver,
                llm_client=self._llm_client,
                embedder=self._embedder,
                cross_encoder=self._cross_encoder,
            )
        return self._graphiti

    @property
    def embedder(self) -> OpenAIEmbedder:
        _ = self.graphiti  # trigger lazy init
        assert self._embedder is not None
        return self._embedder

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        await self.graphiti.build_indices_and_constraints()

    async def close(self) -> None:
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    # ── write ─────────────────────────────────────────────────────────────────

    async def write_episode(
        self,
        name: str,
        body: str | dict,
        saga: str,
        source_description: str = "",
        source: EpisodeType = EpisodeType.json,
        reference_time: Optional[datetime] = None,
        entity_types: Optional[dict[str, type[BaseModel]]] = None,
        edge_types: Optional[dict[str, type[BaseModel]]] = None,
        edge_type_map: Optional[dict[tuple[str, str], list[str]]] = None,
    ) -> dict[str, Any]:
        if isinstance(body, dict):
            body = json.dumps(body)
        effective_entity_types = entity_types or ENTITY_TYPES
        effective_edge_types = edge_types or EDGE_TYPES
        result = await self.graphiti.add_episode(
            name=name,
            episode_body=body,
            source_description=source_description or name,
            source=source,
            reference_time=reference_time or datetime.now(timezone.utc),
            group_id=self.group_id,
            entity_types=effective_entity_types,
            edge_types=effective_edge_types,
            edge_type_map=edge_type_map or EDGE_TYPE_MAP,
            custom_extraction_instructions=build_extraction_instructions(
                entity_types=effective_entity_types,
                edge_types=effective_edge_types,
            ),
            saga=saga,
        )
        return {
            "nodes": len(result.nodes) if hasattr(result, "nodes") else 0,
            "edges": len(result.edges) if hasattr(result, "edges") else 0,
        }

    async def write_episodes_bulk(
        self,
        episodes: list[dict[str, Any]],
        saga: str,
    ) -> dict[str, Any]:
        raw_episodes = []
        for ep in episodes:
            content = ep.get("body", "")
            if isinstance(content, dict):
                content = json.dumps(content)
            raw_episodes.append(
                RawEpisode(
                    name=ep["name"],
                    content=content,
                    source_description=ep.get("source_description", ep["name"]),
                    source=ep.get("source", EpisodeType.json),
                    reference_time=ep.get("reference_time", datetime.now(timezone.utc)),
                )
            )
        if not raw_episodes:
            return {"nodes": 0, "edges": 0}
        return await self.graphiti.add_episode_bulk(
            bulk_episodes=raw_episodes,
            group_id=self.group_id,
            entity_types=ENTITY_TYPES,
            edge_types=EDGE_TYPES,
            edge_type_map=EDGE_TYPE_MAP,
            custom_extraction_instructions=build_extraction_instructions(
                entity_types=ENTITY_TYPES,
                edge_types=EDGE_TYPES,
            ),
            saga=saga,
        )
    

    # ── search ────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        num_results: int = 10,
        search_filter: Optional[SearchFilters] = None,
        center_node_uuid: Optional[str] = None,
    ) -> list[EntityEdge]:
        return await self.graphiti.search(
            query=query,
            group_ids=[self.group_id],
            num_results=num_results,
            search_filter=search_filter or SearchFilters(),
            center_node_uuid=center_node_uuid,
        )

    async def search_nodes_and_edges(
        self,
        query: str,
        config: Optional[SearchConfig] = None,
        search_filter: Optional[SearchFilters] = None,
        num_results: int = 10,
    ) -> SearchResults:
        search_config = config or COMBINED_HYBRID_SEARCH_RRF
        search_config.limit = num_results
        return await self.graphiti.search_(
            query=query,
            config=search_config,
            group_ids=[self.group_id],
            search_filter=search_filter or SearchFilters(),
        )

    # ── graph queries ─────────────────────────────────────────────────────────

    async def find_node_uuid(self, label: str, name: str) -> Optional[str]:
        try:
            result = await self.execute_query(
                f"MATCH (n:{label} {{name: $name, group_id: $gid}})"
                " RETURN n.uuid AS uuid LIMIT 1",
                name=name,
                gid=self.group_id,
            )
            if result and result[0]:
                row = result[0]
                return row[0] if isinstance(row, (list, tuple)) else row.get("uuid")
        except Exception:
            pass
        return None

    async def count_nodes(self, label: str) -> int:
        try:
            result = await self.execute_query(
                f"MATCH (n:{label} {{group_id: $gid}}) RETURN count(n) AS cnt",
                gid=self.group_id,
            )
            if result and result[0]:
                row = result[0]
                return int(row.get("cnt", 0) if isinstance(row, dict) else row[0])
        except Exception:
            pass
        return 0

    async def count_edges(self) -> int:
        try:
            result = await self.execute_query(
                "MATCH ()-[r]->() WHERE r.group_id = $gid RETURN count(r) AS cnt",
                gid=self.group_id,
            )
            if result and result[0]:
                row = result[0]
                return int(row.get("cnt", 0) if isinstance(row, dict) else row[0])
        except Exception:
            pass
        return 0

    async def get_node_names(self, label: str) -> set[str]:
        try:
            result = await self.execute_query(
                f"MATCH (n:{label} {{group_id: $gid}}) RETURN n.name AS name",
                gid=self.group_id,
            )
            names: set[str] = set()
            if result:
                for row in result:
                    if isinstance(row, dict):
                        names.add(row["name"])
                    elif isinstance(row, (list, tuple)):
                        names.add(row[0])
            return names
        except Exception as e:
            logger.warning("Failed to get %s names: %s", label, e)
        return set()

    async def execute_query(self, cypher: str, **params: Any) -> list:
        result = await self.graphiti.driver.execute_query(cypher, **params)
        if result is None:
            return []
        records, _, _ = result
        return records or []

    async def build_communities(self) -> None:
        await self.graphiti.build_communities(group_ids=[self.group_id])


# ── singleton ─────────────────────────────────────────────────────────────────

_client_instance: Optional[GraphitiClient] = None


def get_graphiti_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    group_id: str = GROUP_ID,
) -> GraphitiClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = GraphitiClient(
            host=host or os.getenv("FALKORDB_HOST", "localhost"),
            port=port or int(os.getenv("FALKORDB_PORT", "6379")),
            group_id=group_id,
        )
    return _client_instance
