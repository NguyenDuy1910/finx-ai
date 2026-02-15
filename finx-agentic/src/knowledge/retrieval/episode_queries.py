"""EpisodeQueries — read-only queries for episodic memory."""

import json
import logging
from typing import Any, Dict, List, Optional

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.graph.schemas.episodes import EpisodeCategory

logger = logging.getLogger(__name__)


class EpisodeQueries:
    """Read-only queries against episodic memory in FalkorDB / Graphiti."""

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

    # ── retrieve ─────────────────────────────────────────────────────

    async def get_episode(self, uuid: str) -> Optional[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (e:Episode {uuid: $uuid})
            RETURN e.uuid AS uuid, e.name AS name, e.content AS content,
                   e.source AS source, e.source_description AS source_description,
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
        self, category: EpisodeCategory, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            WHERE e.content CONTAINS $category
            RETURN e.uuid AS uuid, e.name AS name, e.content AS content,
                   e.source_description AS source_description, e.valid_at AS valid_at
            ORDER BY e.valid_at DESC LIMIT $limit
            """,
            group_id=self._group_id, category=category.value, limit=limit,
        )
        return [self._row_to_dict(r) for r in records]

    async def get_recent_episodes(self, limit: int = 10) -> List[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            RETURN e.uuid AS uuid, e.name AS name, e.content AS content,
                   e.source_description AS source_description, e.valid_at AS valid_at
            ORDER BY e.valid_at DESC LIMIT $limit
            """,
            group_id=self._group_id, limit=limit,
        )
        return [self._row_to_dict(r) for r in records]

    # ── semantic search ──────────────────────────────────────────────

    async def search_similar_episodes(
        self, query: str, top_k: int = 5, threshold: float = 0.6,
        category: Optional[EpisodeCategory] = None,
    ) -> List[Dict[str, Any]]:
        embedding = await self._embed(query)
        if not embedding:
            return []

        category_filter = ""
        params: Dict[str, Any] = {
            "embedding": embedding, "threshold": threshold,
            "top_k": top_k, "group_id": self._group_id,
        }
        if category:
            category_filter = "AND e.content CONTAINS $category"
            params["category"] = category.value

        records = await self._execute(
            f"""
            MATCH (e:Episode {{group_id: $group_id}})
            WHERE e.embedding IS NOT NULL {category_filter}
            WITH e, (2 - vec.cosineDistance(e.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            RETURN e.uuid AS uuid, e.name AS name, e.content AS content,
                   e.source_description AS source_description, e.valid_at AS valid_at, score
            ORDER BY score DESC LIMIT $top_k
            """,
            **params,
        )
        return [{**self._row_to_dict(r), "score": float(r.get("score", 0))} for r in records]

    async def search_similar_queries(
        self, query: str, top_k: int = 5, threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        return await self.search_similar_episodes(
            query=query, top_k=top_k, threshold=threshold,
            category=EpisodeCategory.QUERY_EXECUTION,
        )

    # ── query-specific helpers ───────────────────────────────────────

    async def get_queries_for_table(self, table_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (e:Episode {group_id: $group_id})
            WHERE e.content CONTAINS $table_name AND e.content CONTAINS $category
            RETURN e.uuid AS uuid, e.name AS name, e.content AS content,
                   e.source_description AS source_description, e.valid_at AS valid_at
            ORDER BY e.valid_at DESC LIMIT $limit
            """,
            group_id=self._group_id, table_name=table_name,
            category=EpisodeCategory.QUERY_EXECUTION.value, limit=limit,
        )
        return [self._row_to_dict(r) for r in records]

    async def get_feedback_for_query(self, natural_language: str, limit: int = 5) -> List[Dict[str, Any]]:
        return await self.search_similar_episodes(
            query=natural_language, top_k=limit,
            category=EpisodeCategory.USER_FEEDBACK,
        )

    # ── stats ────────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, int]:
        records = await self._execute(
            "MATCH (e:Episode {group_id: $group_id}) RETURN e.content AS content",
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
