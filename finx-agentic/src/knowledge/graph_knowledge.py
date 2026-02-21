from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import Any, Dict, List, Optional

from agno.knowledge.document import Document

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.retrieval.schema_retrieval import SchemaRetrievalService
from src.knowledge.retrieval.episode_queries import EpisodeQueries

logger = logging.getLogger(__name__)


class GraphKnowledge:

    def __init__(
        self,
        client: GraphitiClient,
        default_database: Optional[str] = None,
        max_results: int = 3,
    ):
        self._client = client
        self._default_database = default_database
        self._max_results = max_results
        self._search = SchemaRetrievalService(client)
        self._episodes = EpisodeQueries(client)

    def build_context(self, **kwargs) -> str:
        return (
            "You have access to a graph knowledge base with database schemas, "
            "table relationships, business terms, query patterns, and query history. "
            "The relevant schema context has been automatically retrieved and "
            "attached as references. Use it directly to answer."
        )

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
            schema_result = await self._search.schema_retrieval(
                query=query,
                database=database,
                top_k=max_results,
                include_patterns=True,
                include_context=True,
            )
        except Exception as e:
            logger.warning("schema_retrieval failed: %s", e)
            return []

        result_dict = schema_result.to_dict()
        documents: List[Document] = []

        for table_ctx in result_dict.get("context", []):
            if isinstance(table_ctx, dict):
                table_name = table_ctx.get("table", "unknown")
                db_name = table_ctx.get("database", database or "")

                columns = table_ctx.get("columns", [])
                partition_keys = table_ctx.get("partition_keys", [])
                related = table_ctx.get("related_tables", [])
                rules = table_ctx.get("business_rules", [])
                codesets = table_ctx.get("codesets", [])

                documents.append(Document(
                    name=table_name,
                    content=json.dumps(table_ctx, default=str, ensure_ascii=False),
                    meta_data={
                        "type": "table_context",
                        "database": db_name,
                        "domain": table_ctx.get("domain", ""),
                        "column_count": len(columns),
                        "partition_keys": partition_keys,
                        "related_table_count": len(related),
                        "has_business_rules": len(rules) > 0,
                        "has_codesets": len(codesets) > 0,
                    },
                ))

        if not documents:
            for ranked in result_dict.get("ranked_results", []):
                if isinstance(ranked, dict):
                    documents.append(Document(
                        name=ranked.get("name", "unknown"),
                        content=json.dumps(ranked, default=str, ensure_ascii=False),
                        meta_data={
                            "type": "ranked_result",
                            "database": ranked.get("database", database or ""),
                        },
                    ))

            for tbl in result_dict.get("tables", []):
                if isinstance(tbl, dict):
                    documents.append(Document(
                        name=tbl.get("name", "unknown"),
                        content=json.dumps(tbl, default=str, ensure_ascii=False),
                        meta_data={"type": "table_schema"},
                    ))

        for col in result_dict.get("columns", [])[:10]:
            if isinstance(col, dict):
                documents.append(Document(
                    name=f"column_{col.get('name', 'unknown')}",
                    content=json.dumps(col, default=str, ensure_ascii=False),
                    meta_data={"type": "column"},
                ))

        for ent in result_dict.get("entities", [])[:5]:
            if isinstance(ent, dict):
                documents.append(Document(
                    name=f"entity_{ent.get('name', 'unknown')}",
                    content=json.dumps(ent, default=str, ensure_ascii=False),
                    meta_data={"type": "entity"},
                ))

        for pat in result_dict.get("patterns", [])[:3]:
            if isinstance(pat, dict):
                documents.append(Document(
                    name=f"pattern_{pat.get('intent', 'unknown')}",
                    content=json.dumps(pat, default=str, ensure_ascii=False),
                    meta_data={"type": "query_pattern"},
                ))

        try:
            similar_queries = await self._episodes.search_similar_queries(
                query, top_k=3,
            )
            for sq in similar_queries:
                if isinstance(sq, dict):
                    documents.append(Document(
                        name=f"past_query_{sq.get('id', 'unknown')}",
                        content=json.dumps(sq, default=str, ensure_ascii=False),
                        meta_data={"type": "similar_query"},
                    ))
        except Exception as e:
            logger.debug("similar_queries lookup failed: %s", e)

        if result_dict.get("query_analysis"):
            documents.append(Document(
                name="query_analysis",
                content=json.dumps(result_dict["query_analysis"], default=str, ensure_ascii=False),
                meta_data={"type": "query_analysis"},
            ))

        logger.info(
            "aretrieve completed: %d documents (tables=%d, columns=%d, entities=%d, patterns=%d)",
            len(documents),
            len(result_dict.get("context", [])) or len(result_dict.get("tables", [])),
            len(result_dict.get("columns", [])),
            len(result_dict.get("entities", [])),
            len(result_dict.get("patterns", [])),
        )
        return documents

    @property
    def search(self) -> SchemaRetrievalService:
        return self._search

    @property
    def episodes(self) -> EpisodeQueries:
        return self._episodes
    


