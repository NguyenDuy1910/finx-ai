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
from src.knowledge.retrieval.analyzer import QueryAnalyzer

logger = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_lock = threading.Lock()


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    """Return a long-lived event loop running in a daemon thread."""
    global _loop, _loop_thread
    if _loop is not None and not _loop.is_closed():
        return _loop
    with _lock:
        # double-check after acquiring the lock
        if _loop is not None and not _loop.is_closed():
            return _loop
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
        return _loop


def _run_async(coro):
    """Schedule *coro* on the persistent background loop and block until done."""
    loop = _get_or_create_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


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
        self.episode_store = self.memory.episodes
        self.entity_registry = self.memory.entities
        self._analyzer = QueryAnalyzer()

        tools: List[Any] = [
            self.search_schema,
            self.smart_search,
            self.get_table_details,
            self.get_table_columns,
            self.resolve_business_term,
            self.find_related_tables,
            self.find_join_path,
            self.get_query_patterns,
            self.get_similar_queries,
            self.get_recent_queries,
            self.discover_domains,
            self.analyze_query,
            self.store_query_episode,
            self.store_feedback,
            self.store_pattern,
            self.get_memory_stats,
        ]
        super().__init__(name="graph_search_tools", tools=tools, **kwargs)

    @agentops_tool(name="SearchSchema")
    def search_schema(self, query: str, database: Optional[str] = None) -> str:
        """Search the knowledge graph for tables, columns, entities and patterns
        matching the query.  Uses multi-level retrieval: exact match, graph
        expansion, pattern match and vector similarity, followed by intelligent
        reranking."""
        db = database or self.default_database
        results = _run_async(self.search_service.search_all(query, db))
        return json.dumps(results, default=str, ensure_ascii=False)

    @agentops_tool(name="SmartSearch")
    def smart_search(self, query: str, database: Optional[str] = None, top_k: int = 5) -> str:
        """Advanced multi-level search with full query analysis, reranking and
        fallback strategies.  Returns ranked results with scoring breakdown,
        query analysis metadata and search diagnostics.

        Use this when the simpler search_schema does not return good results
        or when you need detailed scoring information."""
        db = database or self.default_database
        result = _run_async(
            self.search_service.search_schema(query, top_k=top_k, database=db)
        )
        response: Dict[str, Any] = {
            "query_analysis": result.query_analysis,
            "ranked_results": result.ranked_results,
            "search_metadata": result.search_metadata,
            "tables": [r.to_dict() for r in result.tables],
            "entities": [r.to_dict() for r in result.entities],
            "patterns": result.patterns,
            "context": result.context,
        }
        return json.dumps(response, default=str, ensure_ascii=False)

    @agentops_tool(name="GetTableDetails")
    def get_table_details(self, table_name: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        table_info = _run_async(
            self.entity_registry.get_table(table_name, db)
        )
        columns = _run_async(
            self.entity_registry.get_columns_for_table(table_name, db)
        )
        edges = _run_async(
            self.entity_registry.search_entity_edges(table_name)
        )
        return json.dumps({
            "table": table_info,
            "columns": columns,
            "edges": edges,
        }, default=str, ensure_ascii=False)

    @agentops_tool(name="GetTableColumns")
    def get_table_columns(self, table_name: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        columns = _run_async(
            self.entity_registry.get_columns_for_table(table_name, db)
        )
        return json.dumps(columns, default=str, ensure_ascii=False)

    @agentops_tool(name="ResolveBusinessTerm")
    def resolve_business_term(self, term: str) -> str:
        results = _run_async(self.entity_registry.resolve_term(term))
        return json.dumps(results, default=str, ensure_ascii=False)

    @agentops_tool(name="FindRelatedTables")
    def find_related_tables(self, table_name: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        related = _run_async(
            self.entity_registry.find_related_tables(table_name, db)
        )
        return json.dumps({"relations": related}, default=str, ensure_ascii=False)

    @agentops_tool(name="FindJoinPath")
    def find_join_path(self, source_table: str, target_table: str, database: Optional[str] = None) -> str:
        db = database or self.default_database
        source_rels = _run_async(
            self.entity_registry.find_related_tables(source_table, db)
        )
        target_rels = _run_async(
            self.entity_registry.find_related_tables(target_table, db)
        )

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
    def get_query_patterns(self, query: str) -> str:
        patterns = _run_async(
            self.entity_registry.search_patterns(query)
        )
        similar = _run_async(
            self.episode_store.search_similar_queries(query, top_k=3)
        )
        return json.dumps({
            "patterns": patterns,
            "similar_queries": similar,
        }, default=str, ensure_ascii=False)

    @agentops_tool(name="GetSimilarQueries")
    def get_similar_queries(self, query: str, top_k: int = 5) -> str:
        similar = _run_async(
            self.episode_store.search_similar_queries(query, top_k=top_k)
        )
        return json.dumps(similar, default=str, ensure_ascii=False)

    def get_recent_queries(self, limit: int = 10) -> str:
        episodes = _run_async(
            self.episode_store.get_episodes_by_category(
                EpisodeCategory.QUERY_EXECUTION, limit=limit
            )
        )
        return json.dumps(episodes, default=str, ensure_ascii=False)

    @agentops_tool(name="DiscoverDomains")
    def discover_domains(self) -> str:
        """List all available business domains with their tables and entities.
        Useful when no specific search yields results – presents available
        domains so the user can refine their question."""
        domains = _run_async(
            self.search_service._fallback_domain_discovery()
        )
        return json.dumps({"domains": domains}, default=str, ensure_ascii=False)

    @agentops_tool(name="AnalyzeQuery")
    def analyze_query(self, query: str) -> str:
        """Analyse a natural-language query to extract intent, entities,
        complexity, temporal context and business terms WITHOUT hitting
        the graph.  Useful for planning which tools to call next."""
        from dataclasses import asdict
        analysis = self._analyzer.analyze(query)
        return json.dumps(asdict(analysis), default=str, ensure_ascii=False)

    @agentops_tool(name="StoreQueryEpisode")
    def store_query_episode(
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
        episode_id = _run_async(
            self.memory.record_query(
                natural_language=natural_language,
                generated_sql=generated_sql,
                tables_used=tables_used or [],
                database=db,
                intent=intent,
                success=success,
                error_message=error_message,
            )
        )
        return json.dumps({"episode_id": episode_id, "status": "stored"})

    @agentops_tool(name="StoreFeedback")
    def store_feedback(
        self,
        natural_language: str,
        generated_sql: str,
        feedback: str,
        rating: Optional[int] = None,
        corrected_sql: str = "",
    ) -> str:
        episode_id = _run_async(
            self.memory.record_feedback(
                natural_language=natural_language,
                generated_sql=generated_sql,
                feedback=feedback,
                rating=rating,
                corrected_sql=corrected_sql,
            )
        )
        return json.dumps({"episode_id": episode_id, "status": "stored"})

    @agentops_tool(name="StorePattern")
    def store_pattern(
        self,
        intent: str,
        pattern: str,
        sql_template: str,
        tables_involved: Optional[List[str]] = None,
        example_queries: Optional[List[str]] = None,
    ) -> str:
        episode_id = _run_async(
            self.memory.record_pattern(
                intent=intent,
                pattern=pattern,
                sql_template=sql_template,
                tables_involved=tables_involved,
                example_queries=example_queries,
            )
        )
        return json.dumps({"episode_id": episode_id, "status": "stored"})

    def get_memory_stats(self) -> str:
        stats = _run_async(self.memory.get_stats())
        return json.dumps(stats, default=str, ensure_ascii=False)

    async def get_full_context(self, query: str, database: Optional[str] = None) -> Dict[str, Any]:
        db = database or self.default_database
        return await self.memory.get_context(query, database=db)

