from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.knowledge.memory import MemoryManager
from src.knowledge.indexing.schema_indexer import SchemaIndexer
from src.knowledge.graph.client import GraphitiClient

logger = logging.getLogger(__name__)


class IndexingService:

    def __init__(self, client: GraphitiClient, memory: MemoryManager):
        self._client = client
        self._memory = memory
        self._indexer = SchemaIndexer(client)

    async def index_schemas(
        self,
        schema_path: str,
        database: Optional[str] = None,
        skip_existing: bool = False,
    ) -> Dict[str, Any]:
        stats = await self._indexer.load_directory(
            schema_path=schema_path,
            database=database,
            skip_existing=skip_existing,
        )
        return stats

    async def initialize_graph(self) -> None:
        await self._client.initialize()

    async def get_stats(self) -> Dict[str, Any]:
        return await self._memory.get_stats()

    async def record_feedback(
        self,
        natural_language: str,
        generated_sql: str,
        feedback: str,
        rating: Optional[int] = None,
        corrected_sql: str = "",
    ) -> str:
        return await self._memory.record_feedback(
            natural_language=natural_language,
            generated_sql=generated_sql,
            feedback=feedback,
            rating=rating,
            corrected_sql=corrected_sql,
        )
