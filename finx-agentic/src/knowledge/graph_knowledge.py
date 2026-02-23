from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import re
from typing import Any, Dict, List, Optional

from agno.knowledge.document import Document

from src.core.log_tracker import log_tracker
from src.knowledge.graph.client import GraphitiClient
from src.knowledge.retrieval.schema_retrieval import SchemaRetrievalService
from src.knowledge.retrieval.episode_queries import EpisodeQueries

logger = logging.getLogger(__name__)


def _extract_intent_analysis(text: str) -> tuple[Optional[Dict[str, Any]], str]:
    """Extract <intent_analysis> JSON block from query text.

    Returns (parsed_dict_or_None, cleaned_query_without_block).
    """
    pattern = r"<intent_analysis>\s*(\{.*?\})\s*</intent_analysis>"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None, text

    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        logger.debug("Failed to parse intent_analysis JSON block")
        return None, text

    # Remove the block from the query text so retrieval sees clean text
    cleaned = text[: match.start()].strip() + " " + text[match.end() :].strip()
    cleaned = cleaned.strip()
    return data, cleaned


@log_tracker(level="DEBUG", log_args=True, log_result=True)
class GraphKnowledge:

    def __init__(
        self,
        client: GraphitiClient,
        max_results: int = 3,
    ):
        self._client = client
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

    async def aretrieve(self, input: str, **kwargs) -> List[Document]:
        """Retrieve schema context using embedding-first + graph neighborhood search.

        The query is embedded and used for vector similarity across all graph
        layers.  No keyword matching — discovery happens via cosine similarity
        and edge traversal (SYNONYM, ENTITY_MAPPING, JOIN, FK, BELONGS_TO_DOMAIN).

        Intent analysis (if present) provides ``domain`` hint and reranker
        ``weight_overrides`` to steer scoring, but does NOT produce keyword
        search terms.
        """

        # ── Extract intent analysis from embedded XML block (if present) ──
        intent_data, clean_query = _extract_intent_analysis(input)

        max_results = kwargs.get("max_results", self._max_results)

        # Intent hints — used for domain anchoring and reranker weight tuning
        intent = kwargs.get("intent") or (intent_data.get("intent") if intent_data else None)
        domain = kwargs.get("domain") or (intent_data.get("domain") if intent_data else None)
        column_hints = kwargs.get("column_hints") or (intent_data.get("column_hints") if intent_data else None)

        # Weight overrides from LLM intent analysis → steer reranker scoring
        weight_overrides = kwargs.get("weight_overrides") or kwargs.get("weight_hints")
        if not weight_overrides and intent_data:
            raw_weights = intent_data.get("weight_hints", {})
            if raw_weights and isinstance(raw_weights, dict):
                weight_overrides = {k: v for k, v in raw_weights.items() if v is not None}

        try:
            schema_result = await self._search.schema_retrieval(
                query=clean_query,
                top_k=max_results,
                intent=intent,
                domain=domain,
                column_hints=column_hints,
                weight_overrides=weight_overrides,
                include_patterns=True,
                include_context=True,
            )
        except Exception as e:
            logger.warning("schema_retrieval failed: %s", e)
            return []

        result_dict = schema_result.to_dict()
        documents: List[Document] = []

        # ── Primary: full table context documents ──
        for table_ctx in result_dict.get("context", []):
            if isinstance(table_ctx, dict):
                table_name = table_ctx.get("table", "unknown")

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
                        "domain": table_ctx.get("domain", ""),
                        "column_count": len(columns),
                        "partition_keys": partition_keys,
                        "related_table_count": len(related),
                        "has_business_rules": len(rules) > 0,
                        "has_codesets": len(codesets) > 0,
                    },
                ))

        # ── Fallback: ranked results when no full context available ──
        if not documents:
            for ranked in result_dict.get("ranked_results", []):
                if isinstance(ranked, dict):
                    documents.append(Document(
                        name=ranked.get("name", "unknown"),
                        content=json.dumps(ranked, default=str, ensure_ascii=False),
                        meta_data={
                            "type": "ranked_result",
                            "label": ranked.get("label", ""),
                            "score": ranked.get("final_score", 0),
                            "match_type": ranked.get("match_type", ""),
                            "source_layer": ranked.get("source_layer", ""),
                        },
                    ))

        # ── Supplementary: columns, entities, patterns ──
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
                    name=f"pattern_{pat.get('name', 'unknown')}",
                    content=json.dumps(pat, default=str, ensure_ascii=False),
                    meta_data={"type": "query_pattern"},
                ))

        # ── Similar past queries ──
        try:
            similar_queries = await self._episodes.search_similar_queries(
                clean_query, top_k=3,
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

        # ── Search metadata for debugging ──
        if result_dict.get("query_analysis"):
            documents.append(Document(
                name="query_analysis",
                content=json.dumps(result_dict["query_analysis"], default=str, ensure_ascii=False),
                meta_data={"type": "query_analysis"},
            ))

        if result_dict.get("search_metadata"):
            documents.append(Document(
                name="search_metadata",
                content=json.dumps(result_dict["search_metadata"], default=str, ensure_ascii=False),
                meta_data={"type": "search_metadata"},
            ))

        logger.info(
            "aretrieve completed: %d documents (tables=%d, columns=%d, entities=%d, patterns=%d) "
            "[%s]",
            len(documents),
            len(result_dict.get("context", [])) or len(result_dict.get("tables", [])),
            len(result_dict.get("columns", [])),
            len(result_dict.get("entities", [])),
            len(result_dict.get("patterns", [])),
            result_dict.get("search_metadata", {}).get("layers_executed", ""),
        )
        return documents

    @property
    def search(self) -> SchemaRetrievalService:
        return self._search

    @property
    def episodes(self) -> EpisodeQueries:
        return self._episodes
    


