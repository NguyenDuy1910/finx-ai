from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from agno.knowledge.document import Document

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.memory import MemoryManager
from src.tools.graph_tools import GraphSearchTools

logger = logging.getLogger(__name__)


class GraphKnowledge:

    def __init__(
        self,
        client: GraphitiClient,
        default_database: Optional[str] = None,
        max_results: int = 5,
    ):
        self._client = client
        self._default_database = default_database
        self._max_results = max_results
        self._memory = MemoryManager(client)
        self._tools = GraphSearchTools(client=client, default_database=default_database)

    def build_context(self, **kwargs) -> str:
        return (
            "You have access to a graph knowledge base with database schemas, "
            "table relationships, business terms, query patterns, and query history. "
            "Before calling any tool, extract entities, intent, domain, "
            "business_terms, and column_hints from the user message."
        )

    def get_tools(self, **kwargs) -> List[Callable]:
        return [
            self._tools.schema_retrieval,
            self._tools.get_table_details,
            self._tools.get_table_columns,
            self._tools.resolve_business_term,
            self._tools.find_related_tables,
            self._tools.find_join_path,
            self._tools.get_query_patterns,
            self._tools.get_similar_queries,
            self._tools.get_recent_queries,
            self._tools.discover_domains,
            self._tools.store_query_episode,
            self._tools.store_feedback,
            self._tools.store_pattern,
            self._tools.get_memory_stats,
        ]

    async def aget_tools(self, **kwargs) -> List[Callable]:
        return self.get_tools()

    def retrieve(self, query: str, **kwargs) -> List[Document]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.aretrieve(query, **kwargs)).result()
        return asyncio.run(self.aretrieve(query, **kwargs))

    async def aretrieve(self, query: str, **kwargs) -> List[Document]:
        max_results = kwargs.get("max_results", self._max_results)
        database = kwargs.get("database", self._default_database)

        try:
            context = await self._memory.get_context(
                query=query, database=database, top_k=max_results,
            )
        except Exception as e:
            logger.warning("Graph knowledge retrieval failed: %s", e)
            return []

        documents: List[Document] = []

        tables = context.get("tables") or context.get("ranked_results", [])
        for table in tables:
            if isinstance(table, dict):
                documents.append(Document(
                    name=table.get("name") or table.get("table_name", "unknown"),
                    content=json.dumps(table, default=str, ensure_ascii=False),
                    meta_data={
                        "type": "table_schema",
                        "database": table.get("database", database or ""),
                        "score": table.get("score", 0),
                    },
                ))

        for sq in context.get("similar_queries", [])[:3]:
            if isinstance(sq, dict):
                documents.append(Document(
                    name=f"past_query_{sq.get('id', 'unknown')}",
                    content=json.dumps(sq, default=str, ensure_ascii=False),
                    meta_data={"type": "similar_query"},
                ))

        for pat in context.get("patterns", [])[:3]:
            if isinstance(pat, dict):
                documents.append(Document(
                    name=f"pattern_{pat.get('intent', 'unknown')}",
                    content=json.dumps(pat, default=str, ensure_ascii=False),
                    meta_data={"type": "query_pattern"},
                ))

        return documents

    def search_docs(self, query: str) -> str:
        # Your search implementation
        return "Results for: " + query

    @property
    def tools(self) -> GraphSearchTools:
        return self._tools

    @property
    def memory(self) -> MemoryManager:
        return self._memory
    


