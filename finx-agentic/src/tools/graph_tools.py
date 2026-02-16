import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit

from src.core.agentops_tracker import tool as agentops_tool
from src.knowledge.graph.client import GraphitiClient
from src.knowledge.memory import MemoryManager
from src.knowledge.graph.schemas.episodes import EpisodeCategory
from src.knowledge.utils.pipeline_logger import track_class

logger = logging.getLogger(__name__)

_lock = threading.Lock()



class GraphSearchTools(Toolkit):

    def __init__(
        self,
        client: GraphitiClient,
        default_database: Optional[str] = None,
        **kwargs,
    ):
        self.gclient = client
        self.default_database = default_database
        self.memory = MemoryManager(client)
        self.search_service = self.memory.search
        self.episode_store = self.memory.episode_queries
        self.entity_registry = self.memory.entity_queries

        tools: List[Any] = [
            self.schema_retrieval,
            self.get_table_details,
            self.get_table_columns,
            self.resolve_business_term,
            self.find_related_tables,
            self.find_join_path,
            self.get_query_patterns,
            self.get_similar_queries,
            self.get_recent_queries,
            self.discover_domains,
            self.store_query_episode,
            self.store_feedback,
            self.store_pattern,
            self.get_memory_stats,
        ]
        super().__init__(name="graph_search_tools", tools=tools, **kwargs)

    @agentops_tool(name="SchemaRetrieval")
    async def schema_retrieval(
        self,
        query: str,
        database: Optional[str] = None,
        entities: Optional[List[str]] = None,
        intent: Optional[str] = None,
        domain: Optional[str] = None,
        business_terms: Optional[List[str]] = None,
        column_hints: Optional[List[str]] = None,
        top_k: int = 3,
        include_patterns: bool = True,
        include_context: bool = True,
    ) -> str:
        """Search the knowledge graph for tables, columns, entities and patterns
        matching the query.  Uses multi-level retrieval: exact match, graph
        expansion, pattern match and vector similarity, followed by intelligent
        reranking.

        Parameters
        ----------
        query : str
            Natural-language search query describing what the user is looking for.
        database : str | None
            Restrict results to a specific database.
        entities : list[str] | None
            Explicit entity or table names already identified from the user
            message (e.g. ["party_v2_public_customer", "transaction"]).
            Providing these uses them directly as Level-1 search terms.
        intent : str | None
            The user intent: "schema_exploration", "data_query",
            "relationship_discovery", or "knowledge_lookup".
            Tailors which retrieval levels execute.
        domain : str | None
            Business domain to focus on (e.g. "payment", "lending", "card",
            "party", "campaign_management").  Filters Level-1 results and
            boosts same-domain items in reranking.
        business_terms : list[str] | None
            Vietnamese or English business terms / synonyms extracted from
            the user message (e.g. ["số dư", "tài khoản"] or
            ["balance", "account"]).  Added to search terms for synonym matching.
        column_hints : list[str] | None
            Column names the user is interested in (e.g. ["cif_number",
            "created_at", "status"]).  Tables containing these columns
            receive a reranking boost.
        top_k : int
            Maximum number of results per category (default 5).
        include_patterns : bool
            Whether to include query pattern results.
        include_context : bool
            Whether to fetch full table context (columns, rules, codesets).
        """
        db = database or self.default_database
        result = await self.search_service.schema_retrieval(
            query, database=db, entities=entities, intent=intent,
            domain=domain, business_terms=business_terms, column_hints=column_hints,
            top_k=top_k, include_patterns=include_patterns,
            include_context=include_context,
        )
        return json.dumps(result.to_dict(), default=str, ensure_ascii=False)

    @agentops_tool(name="GetTableDetails")
    async def get_table_details(self, table_name: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        table_info = await self.entity_registry.get_table(table_name, db)
        columns = await self.entity_registry.get_columns_for_table(table_name, db)
        edges = await self.entity_registry.search_entity_edges(table_name)
        return json.dumps({
            "table": table_info,
            "columns": columns,
            "edges": edges,
        }, default=str, ensure_ascii=False)

    @agentops_tool(name="GetTableColumns")
    async def get_table_columns(self, table_name: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        columns = await self.entity_registry.get_columns_for_table(table_name, db)
        return json.dumps(columns, default=str, ensure_ascii=False)

    @agentops_tool(name="ResolveBusinessTerm")
    async def resolve_business_term(self, term: str) -> str:
        results = await self.entity_registry.resolve_term(term)
        return json.dumps(results, default=str, ensure_ascii=False)

    @agentops_tool(name="FindRelatedTables")
    async def find_related_tables(self, table_name: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        related = await self.entity_registry.find_related_tables(table_name, db)
        return json.dumps({"relations": related}, default=str, ensure_ascii=False)

    @agentops_tool(name="FindJoinPath")
    async def find_join_path(self, source_table: str, target_table: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        source_rels = await self.entity_registry.find_related_tables(source_table, db)
        target_rels = await self.entity_registry.find_related_tables(target_table, db)

        direct = [
            r for r in source_rels
            if target_table.lower() in r.get("table", "").lower()
        ]

        source_tables = {r.get("table", "").lower() for r in source_rels}
        target_tables = {r.get("table", "").lower() for r in target_rels}
        shared = source_tables & target_tables

        return json.dumps({
            "source": source_table,
            "target": target_table,
            "direct_joins": direct,
            "shared_intermediates": list(shared),
            "source_relations": source_rels,
            "target_relations": target_rels,
        }, default=str, ensure_ascii=False)

    @agentops_tool(name="GetQueryPatterns")
    async def get_query_patterns(self, query: str) -> str:
        patterns = await self.entity_registry.search_patterns(query)
        similar = await self.episode_store.search_similar_queries(query, top_k=3)
        return json.dumps({
            "patterns": patterns,
            "similar_queries": similar,
        }, default=str, ensure_ascii=False)

    @agentops_tool(name="GetSimilarQueries")
    async def get_similar_queries(self, query: str, top_k: int = 5) -> str:
        similar = await self.episode_store.search_similar_queries(query, top_k=top_k)
        return json.dumps(similar, default=str, ensure_ascii=False)

    async def get_recent_queries(self, limit: int = 10) -> str:
        episodes = await self.episode_store.get_episodes_by_category(
            EpisodeCategory.QUERY_EXECUTION, limit=limit
        )
        return json.dumps(episodes, default=str, ensure_ascii=False)

    @agentops_tool(name="DiscoverDomains")
    async def discover_domains(self) -> str:
        """List all available business domains with their tables and entities.
        Useful when no specific search yields results – presents available
        domains so the user can refine their question."""
        domains = await self.search_service._fallback_domain_discovery()
        return json.dumps({"domains": domains}, default=str, ensure_ascii=False)

    @agentops_tool(name="StoreQueryEpisode")
    async def store_query_episode(
        self,
        natural_language: str,
        generated_sql: str,
        tables_used: Optional[List[str]] = None,
        database: Optional[str] = None,
        intent: str = "",
        success: bool = True,
        error_message: str = "",
    ) -> str:
        db = database or self.default_database or ""
        episode_id = await self.memory.record_query(
            natural_language=natural_language,
            generated_sql=generated_sql,
            tables_used=tables_used or [],
            database=db,
            intent=intent,
            success=success,
            error_message=error_message,
        )
        return json.dumps({"episode_id": episode_id, "status": "stored"})

    @agentops_tool(name="StoreFeedback")
    async def store_feedback(
        self,
        natural_language: str,
        generated_sql: str,
        feedback: str,
        rating: Optional[int] = None,
        corrected_sql: str = "",
    ) -> str:
        episode_id = await self.memory.record_feedback(
            natural_language=natural_language,
            generated_sql=generated_sql,
            feedback=feedback,
            rating=rating,
            corrected_sql=corrected_sql,
        )
        return json.dumps({"episode_id": episode_id, "status": "stored"})

    @agentops_tool(name="StorePattern")
    async def store_pattern(
        self,
        intent: str,
        pattern: str,
        sql_template: str,
        tables_involved: Optional[List[str]] = None,
        example_queries: Optional[List[str]] = None,
    ) -> str:
        episode_id = await self.memory.record_pattern(
            intent=intent,
            pattern=pattern,
            sql_template=sql_template,
            tables_involved=tables_involved,
            example_queries=example_queries,
        )
        return json.dumps({"episode_id": episode_id, "status": "stored"})

    async def get_memory_stats(self) -> str:
        stats = await self.memory.get_stats()
        return json.dumps(stats, default=str, ensure_ascii=False)

    async def get_full_context(self, query: str, database: Optional[str] = None) -> Dict[str, Any]:
        db = database or self.default_database
        return await self.memory.get_context(query, database=db)

