from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.graph.client import GraphitiClient
from src.knowledge.retrieval import GraphKnowledgeV2

logger = logging.getLogger(__name__)


class SearchService:
    """Schema and graph search service backed directly by GraphitiClient."""

    def __init__(self, client: GraphitiClient) -> None:
        self._client = client
        self._knowledge = GraphKnowledgeV2(client=client, max_results=10)

    async def search_schema(
        self,
        query: str,
        domain: Optional[str] = None,
        entities: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        docs = await self._knowledge.aretrieve(query, max_results=top_k, domain=domain)
        return {
            "query": query,
            "results": [
                {"name": d.name, "content": d.content, "meta": d.meta_data}
                for d in docs
            ],
        }

    async def get_table_details(
        self,
        table_name: str,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        rows = await self._client.execute_query(
            "MATCH (t:Table {name: $name, group_id: $gid}) "
            "OPTIONAL MATCH (t)-[:STORED_IN]-(c:Column) "
            "RETURN t, collect(c) AS columns LIMIT 1",
            name=table_name,
            gid=self._client.group_id,
        )
        if not rows:
            return {"error": f"Table '{table_name}' not found"}
        row = rows[0]
        return row if isinstance(row, dict) else {"raw": str(row)}

    async def find_related_tables(
        self,
        table_name: str,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        rows = await self._client.execute_query(
            "MATCH (t:Table {name: $name})-[r]-(related:Table) "
            "RETURN related.name AS table, type(r) AS relationship LIMIT 20",
            name=table_name,
        )
        return {"relations": rows or []}

    async def find_join_path(
        self,
        source: str,
        target: str,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        direct = await self._client.execute_query(
            "MATCH (s:Table {name: $source})-[r]-(t:Table {name: $target}) "
            "RETURN type(r) AS relationship",
            source=source, target=target,
        )
        shared = await self._client.execute_query(
            "MATCH (s:Table {name: $source})-[]-(mid:Table)-[]-(t:Table {name: $target}) "
            "RETURN DISTINCT mid.name AS intermediate LIMIT 10",
            source=source, target=target,
        )
        return {
            "source": source,
            "target": target,
            "direct_joins": direct or [],
            "shared_intermediates": [
                r.get("intermediate", "") for r in (shared or []) if isinstance(r, dict)
            ],
        }

    async def resolve_term(self, term: str) -> Dict[str, Any]:
        rows = await self._client.execute_query(
            "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($term) "
            "RETURN n.name AS name, labels(n) AS labels, n.summary AS summary LIMIT 10",
            term=term,
        )
        return {"results": rows or []}

    async def discover_domains(self) -> Dict[str, Any]:
        rows = await self._client.execute_query(
            "MATCH (pa:ProductArea) RETURN pa.name AS name, pa.summary AS description"
        )
        return {"domains": rows or []}

    async def get_similar_queries(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        docs = await self._knowledge.aretrieve(query, max_results=top_k)
        return [
            {"name": d.name, "content": d.content, "score": d.meta_data.get("score", 0)}
            for d in docs
            if d.meta_data.get("type") in ("query_pattern", "relationship")
        ]

    async def get_query_patterns(self, query: str) -> Dict[str, Any]:
        results = await self.get_similar_queries(query, top_k=3)
        return {"similar_queries": results}
