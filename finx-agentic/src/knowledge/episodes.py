import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from graphiti_core.nodes import EpisodicNode, EpisodeType

from src.knowledge.client import GraphitiClient
from src.knowledge.models.episodes import (
    EpisodeCategory,
    FeedbackEpisode,
    PatternEpisode,
    QueryEpisode,
    SchemaEpisode,
)

logger = logging.getLogger(__name__)


class EpisodeStore:
    """Persistent store for episodic memory backed by FalkorDB / Graphiti."""

    def __init__(self, client: GraphitiClient):
        self._client = client

    @property
    def _driver(self):
        return self._client.graphiti.driver

    @property
    def _embedder(self):
        # accessing .graphiti lazily initializes the client
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
    # store
    # ------------------------------------------------------------------

    async def store_schema_episode(self, episode: SchemaEpisode) -> str:
        """Persist a schema-definition episode and return its uuid."""
        node = episode.to_episodic_node(self._group_id)
        return await self._persist_episode(node)

    async def store_query_episode(self, episode: QueryEpisode) -> str:
        """Persist a query-execution episode and return its uuid."""
        node = episode.to_episodic_node(self._group_id)
        return await self._persist_episode(node)

    async def store_feedback_episode(self, episode: FeedbackEpisode) -> str:
        """Persist a user-feedback episode and return its uuid."""
        node = episode.to_episodic_node(self._group_id)
        return await self._persist_episode(node)

    async def store_pattern_episode(self, episode: PatternEpisode) -> str:
        """Persist a pattern-learned episode and return its uuid."""
        node = episode.to_episodic_node(self._group_id)
        return await self._persist_episode(node)

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
        logger.debug("Stored episode %s (%s)", node.name, node.uuid)
        return node.uuid

    # ------------------------------------------------------------------
    # retrieve
    # ------------------------------------------------------------------

    async def get_episode(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single episode by uuid."""
        records = await self._execute(
            """
            MATCH (e:Episode {uuid: $uuid})
            RETURN e.uuid AS uuid,
                   e.name AS name,
                   e.content AS content,
                   e.source AS source,
                   e.source_description AS source_description,
                   e.valid_at AS valid_at
            """,
            uuid=uuid,
        )
        if not records:
            return None
        row = records[0]
        content = json.loads(row["content"]) if row.get("content") else {}
        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "category": content.get("category"),
            "content": content,
            "source": row.get("source"),
            "source_description": row.get("source_description"),
            "valid_at": row.get("valid_at"),
        }

    async def get_episodes_by_category(
        self,
        category: EpisodeCategory,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return the most-recent episodes of a given category."""
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            WHERE e.content CONTAINS $category
            RETURN e.uuid AS uuid,
                   e.name AS name,
                   e.content AS content,
                   e.source_description AS source_description,
                   e.valid_at AS valid_at
            ORDER BY e.valid_at DESC
            LIMIT $limit
            """,
            group_id=self._group_id,
            category=category.value,
            limit=limit,
        )
        return [self._row_to_dict(r) for r in records]

    async def get_recent_episodes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the N most-recent episodes regardless of category."""
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            RETURN e.uuid AS uuid,
                   e.name AS name,
                   e.content AS content,
                   e.source_description AS source_description,
                   e.valid_at AS valid_at
            ORDER BY e.valid_at DESC
            LIMIT $limit
            """,
            group_id=self._group_id,
            limit=limit,
        )
        return [self._row_to_dict(r) for r in records]

    # ------------------------------------------------------------------
    # semantic search over episodes
    # ------------------------------------------------------------------

    async def search_similar_episodes(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.6,
        category: Optional[EpisodeCategory] = None,
    ) -> List[Dict[str, Any]]:
        """Vector-similarity search across episodes."""
        embedding = await self._embed(query)
        if not embedding:
            return []

        category_filter = ""
        params: Dict[str, Any] = {
            "embedding": embedding,
            "threshold": threshold,
            "top_k": top_k,
            "group_id": self._group_id,
        }
        if category:
            category_filter = "AND e.content CONTAINS $category"
            params["category"] = category.value

        records = await self._execute(
            f"""
            MATCH (e:Episode {{group_id: $group_id}})
            WHERE e.embedding IS NOT NULL {category_filter}
            WITH e,
                 (2 - vec.cosineDistance(e.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            RETURN e.uuid AS uuid,
                   e.name AS name,
                   e.content AS content,
                   e.source_description AS source_description,
                   e.valid_at AS valid_at,
                   score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            **params,
        )
        return [
            {**self._row_to_dict(r), "score": float(r.get("score", 0))}
            for r in records
        ]

    async def search_similar_queries(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Find past query episodes that are semantically similar."""
        return await self.search_similar_episodes(
            query=query,
            top_k=top_k,
            threshold=threshold,
            category=EpisodeCategory.QUERY_EXECUTION,
        )

    # ------------------------------------------------------------------
    # query-specific helpers
    # ------------------------------------------------------------------

    async def get_queries_for_table(
        self,
        table_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return query episodes that used a specific table."""
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            WHERE e.content CONTAINS $table_name
                  AND e.content CONTAINS $category
            RETURN e.uuid AS uuid,
                   e.name AS name,
                   e.content AS content,
                   e.source_description AS source_description,
                   e.valid_at AS valid_at
            ORDER BY e.valid_at DESC
            LIMIT $limit
            """,
            group_id=self._group_id,
            table_name=table_name,
            category=EpisodeCategory.QUERY_EXECUTION.value,
            limit=limit,
        )
        return [self._row_to_dict(r) for r in records]

    async def get_feedback_for_query(
        self,
        natural_language: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find feedback episodes related to a particular question."""
        return await self.search_similar_episodes(
            query=natural_language,
            top_k=limit,
            category=EpisodeCategory.USER_FEEDBACK,
        )

    # ------------------------------------------------------------------
    # deletion
    # ------------------------------------------------------------------

    async def delete_episode(self, uuid: str) -> bool:
        """Remove a single episode."""
        await self._execute(
            "MATCH (e:Episode {uuid: $uuid}) DELETE e",
            uuid=uuid,
        )
        logger.info("Deleted episode %s", uuid)
        return True

    async def delete_episodes_by_category(self, category: EpisodeCategory) -> int:
        """Remove all episodes of a given category.  Returns count deleted."""
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            WHERE e.content CONTAINS $category
            WITH e, count(e) AS cnt
            DELETE e
            RETURN cnt
            """,
            group_id=self._group_id,
            category=category.value,
        )
        count = records[0]["cnt"] if records else 0
        logger.info("Deleted %d episodes of category %s", count, category.value)
        return count

    # ------------------------------------------------------------------
    # stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> Dict[str, int]:
        """Return counts of episodes per category."""
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            RETURN e.content AS content
            """,
            group_id=self._group_id,
        )
        stats: Dict[str, int] = {}
        for r in records:
            try:
                cat = json.loads(r["content"]).get("category", "unknown")
            except Exception:
                cat = "unknown"
            stats[cat] = stats.get(cat, 0) + 1
        return stats

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: Dict) -> Dict[str, Any]:
        content = json.loads(row["content"]) if row.get("content") else {}
        return {
            "uuid": row.get("uuid"),
            "name": row.get("name"),
            "category": content.get("category"),
            "content": content,
            "source_description": row.get("source_description"),
            "valid_at": row.get("valid_at"),
        }
