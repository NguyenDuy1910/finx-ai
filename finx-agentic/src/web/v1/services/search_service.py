from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.knowledge.memory import MemoryManager

logger = logging.getLogger(__name__)


class SearchService:

    def __init__(self, memory: MemoryManager):
        self._memory = memory
        self._search = memory.search
        self._entities = memory.entity_queries
        self._episodes = memory.episode_queries

    async def search_schema(
        self,
        query: str,
        domain: Optional[str] = None,
        entities: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        result = await self._memory.schema_retrieval(
            query=query,
            domain=domain,
            entities=entities,
            top_k=top_k,
        )
        return result.to_dict()

    async def get_table_details(
        self,
        table_name: str,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        table_info = await self._entities.get_table(table_name, database)
        columns = await self._entities.get_columns_for_table(table_name, database)
        edges = await self._entities.search_entity_edges(table_name)
        return {"table": table_info, "columns": columns, "edges": edges}

    async def find_related_tables(
        self,
        table_name: str,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        related = await self._entities.find_related_tables(table_name, database)
        return {"relations": related}

    async def find_join_path(
        self,
        source: str,
        target: str,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        source_rels = await self._entities.find_related_tables(source, database)
        target_rels = await self._entities.find_related_tables(target, database)
        direct = [
            r for r in source_rels
            if target.lower() in r.get("table", "").lower()
        ]
        source_tables = {r.get("table", "").lower() for r in source_rels}
        target_tables = {r.get("table", "").lower() for r in target_rels}
        shared = source_tables & target_tables
        return {
            "source": source,
            "target": target,
            "direct_joins": direct,
            "shared_intermediates": list(shared),
        }

    async def resolve_term(self, term: str) -> Dict[str, Any]:
        results = await self._entities.resolve_term(term)
        return results

    async def discover_domains(self) -> Dict[str, Any]:
        domains = await self._search.discover_domains()
        return {"domains": domains}

    async def get_similar_queries(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return await self._episodes.search_similar_queries(query, top_k=top_k)

    async def get_query_patterns(self, query: str) -> Dict[str, Any]:
        patterns = await self._entities.search_patterns(query)
        similar = await self._episodes.search_similar_queries(query, top_k=3)
        return {"patterns": patterns, "similar_queries": similar}
