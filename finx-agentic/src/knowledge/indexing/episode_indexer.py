"""EpisodeIndexer — write-side persistent store for episodic memory."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from graphiti_core.nodes import EpisodicNode, EpisodeType

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph.schemas.episodes import (
    EpisodeCategory,
    FeedbackEpisode,
    PatternEpisode,
    QueryEpisode,
    SchemaEpisode,
)

logger = logging.getLogger(__name__)


class EpisodeIndexer:
    """Write-side persistent store for episodic memory backed by FalkorDB / Graphiti."""

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

    # ── store ────────────────────────────────────────────────────────

    async def store_schema_episode(self, episode: SchemaEpisode) -> str:
        return await self._persist_episode(episode.to_episodic_node(self._group_id))

    async def store_query_episode(self, episode: QueryEpisode) -> str:
        return await self._persist_episode(episode.to_episodic_node(self._group_id))

    async def store_feedback_episode(self, episode: FeedbackEpisode) -> str:
        return await self._persist_episode(episode.to_episodic_node(self._group_id))

    async def store_pattern_episode(self, episode: PatternEpisode) -> str:
        return await self._persist_episode(episode.to_episodic_node(self._group_id))

    async def _persist_episode(self, node: EpisodicNode) -> str:
        description = (node.source_description or node.content or "").replace("\n", " ").strip()
        embedding = await self._embed(description) if description else []

        await self._execute(
            """
            MERGE (e:Episode {name: $name, group_id: $group_id})
            SET e.uuid         = $uuid,
                e.source        = $source,
                e.source_description = $source_description,
                e.content       = $content,
                e.valid_at      = $valid_at,
                e.created_at    = $created_at,
                e.embedding     = vecf32($embedding)
            """,
            uuid=node.uuid,
            name=node.name,
            group_id=node.group_id,
            source=node.source.value if isinstance(node.source, EpisodeType) else str(node.source),
            source_description=node.source_description or "",
            content=node.content or "",
            valid_at=node.valid_at.isoformat() if node.valid_at else datetime.now(timezone.utc).isoformat(),
            created_at=node.created_at.isoformat() if hasattr(node, "created_at") and node.created_at else datetime.now(timezone.utc).isoformat(),
            embedding=embedding,
        )
        return node.uuid

    # ── deletion ─────────────────────────────────────────────────────

    async def delete_episode(self, uuid: str) -> bool:
        await self._execute("MATCH (e:Episode {uuid: $uuid}) DELETE e", uuid=uuid)
        return True

    async def delete_episodes_by_category(self, category: EpisodeCategory) -> int:
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            WHERE e.content CONTAINS $category
            WITH e, count(e) AS cnt DELETE e RETURN cnt
            """,
            group_id=self._group_id, category=category.value,
        )
        return records[0]["cnt"] if records else 0
