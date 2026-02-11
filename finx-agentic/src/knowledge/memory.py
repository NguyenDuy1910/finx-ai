import logging
from typing import Any, Dict, List, Optional

from src.knowledge.client import GraphitiClient
from src.knowledge.episodes import EpisodeStore
from src.knowledge.entities import EntityRegistry
from src.knowledge.search import SemanticSearchService, SchemaSearchResult
from src.knowledge.models.episodes import (
    EpisodeCategory,
    FeedbackEpisode,
    PatternEpisode,
    QueryEpisode,
    SchemaEpisode,
)
from src.knowledge.models.nodes import (
    BusinessEntityNode,
    ColumnNode,
    QueryPatternNode,
    TableNode,
)
from src.knowledge.models.edges import (
    EntityMappingEdge,
    ForeignKeyEdge,
    HasColumnEdge,
    JoinEdge,
    QueryPatternEdge,
)

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Unified façade over the graph-based memory system.

    Usage::

        client = get_graphiti_client()
        memory = MemoryManager(client)

        # record a query
        await memory.record_query(
            natural_language="total card transactions today",
            generated_sql="SELECT count(*) FROM vk_card_tnx ...",
            tables_used=["vk_card_tnx"],
            database="gold_zone",
            intent="aggregation",
        )

        # retrieve context for a new question
        ctx = await memory.get_context("card transaction fees")
    """

    def __init__(self, client: GraphitiClient):
        self._client = client
        self.episodes = EpisodeStore(client)
        self.entities = EntityRegistry(client)
        self.search = SemanticSearchService(client)

    # ------------------------------------------------------------------
    # initialisation
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Build graph indices / constraints and vector indexes."""
        await self._client.initialize()
        await self._create_episode_vector_index()
        await self._create_pattern_vector_index()
        logger.info("MemoryManager initialised")

    async def _create_episode_vector_index(self) -> None:
        driver = self._client.graphiti.driver
        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (e:Episode) ON (e.embedding)"
            )
            logger.info("Created vector index for Episode.embedding")
        except Exception as e:
            logger.debug("Episode vector index already exists: %s", e)

    async def _create_pattern_vector_index(self) -> None:
        driver = self._client.graphiti.driver
        try:
            await driver.execute_query(
                "CREATE VECTOR INDEX FOR (p:QueryPattern) ON (p.embedding)"
            )
            logger.info("Created vector index for QueryPattern.embedding")
        except Exception as e:
            logger.debug("QueryPattern vector index already exists: %s", e)

    # ------------------------------------------------------------------
    # record events (episodic layer)
    # ------------------------------------------------------------------

    async def record_schema(
        self,
        table_name: str,
        database: str,
        columns: List[Dict[str, Any]],
        partition_keys: Optional[List[str]] = None,
        description: str = "",
        action: str = "created",
    ) -> str:
        """Record a schema event *and* upsert the corresponding entities."""
        episode = SchemaEpisode(
            table_name=table_name,
            database=database,
            columns=columns,
            partition_keys=partition_keys or [],
            description=description,
            action=action,
        )
        episode_id = await self.episodes.store_schema_episode(episode)

        # also upsert the entity nodes so they're searchable
        table = TableNode(
            name=table_name,
            database=database,
            description=description,
            partition_keys=partition_keys or [],
        )
        table_entity = await self.entities.register_table(table)

        for idx, col in enumerate(columns):
            col_node = ColumnNode(
                name=col["name"],
                table_name=table_name,
                database=database,
                data_type=col.get("type", "string"),
                description=col.get("description", ""),
                is_primary_key=col.get("primary_key", False),
                is_foreign_key=col.get("foreign_key", False),
                is_partition=col["name"] in (partition_keys or []),
                is_nullable=col.get("nullable", True),
                sample_values=col.get("sample_values", []),
            )
            col_entity = await self.entities.register_column(col_node)

            edge = HasColumnEdge(
                table_name=table_name,
                database=database,
                column_name=col["name"],
                ordinal_position=idx,
            )
            await self.entities.register_has_column(
                edge, table_entity.uuid, col_entity.uuid
            )

        logger.info("Recorded schema episode for %s.%s (%s)", database, table_name, action)
        return episode_id

    async def record_query(
        self,
        natural_language: str,
        generated_sql: str,
        tables_used: Optional[List[str]] = None,
        database: str = "",
        intent: str = "",
        success: bool = True,
        execution_time_ms: Optional[int] = None,
        row_count: Optional[int] = None,
        error_message: str = "",
    ) -> str:
        """Record a query-execution episode."""
        episode = QueryEpisode(
            natural_language=natural_language,
            generated_sql=generated_sql,
            tables_used=tables_used or [],
            database=database,
            intent=intent,
            success=success,
            execution_time_ms=execution_time_ms,
            row_count=row_count,
            error_message=error_message,
        )
        episode_id = await self.episodes.store_query_episode(episode)
        logger.info("Recorded query episode: %s", natural_language[:60])
        return episode_id

    async def record_feedback(
        self,
        natural_language: str,
        generated_sql: str,
        feedback: str,
        rating: Optional[int] = None,
        corrected_sql: str = "",
    ) -> str:
        """Record user feedback on a generated query."""
        episode = FeedbackEpisode(
            natural_language=natural_language,
            generated_sql=generated_sql,
            feedback=feedback,
            rating=rating,
            corrected_sql=corrected_sql,
        )
        episode_id = await self.episodes.store_feedback_episode(episode)
        logger.info("Recorded feedback episode: %s", feedback[:60])
        return episode_id

    async def record_pattern(
        self,
        intent: str,
        pattern: str,
        sql_template: str,
        tables_involved: Optional[List[str]] = None,
        example_queries: Optional[List[str]] = None,
    ) -> str:
        """Record a learned query pattern and register it as an entity."""
        episode = PatternEpisode(
            intent=intent,
            pattern=pattern,
            sql_template=sql_template,
            tables_involved=tables_involved or [],
            example_queries=example_queries or [],
        )
        episode_id = await self.episodes.store_pattern_episode(episode)

        # also register as a searchable entity node
        pattern_node = QueryPatternNode(
            name=pattern[:50],
            intent=intent,
            pattern=pattern,
            sql_template=sql_template,
            tables_involved=tables_involved or [],
            frequency=1,
        )
        pattern_entity = await self.entities.register_query_pattern(pattern_node)

        # link pattern → tables
        for tbl in (tables_involved or []):
            table_info = await self.entities.get_table(tbl)
            if table_info:
                edge = QueryPatternEdge(
                    pattern_name=pattern_node.name,
                    table_name=tbl,
                    database="",
                    role="source",
                    frequency=1,
                )
                await self.entities.register_query_pattern_edge(
                    edge, pattern_entity.uuid, table_info["uuid"]
                )

        logger.info("Recorded pattern: %s — %s", intent, pattern[:60])
        return episode_id

    # ------------------------------------------------------------------
    # retrieval  (combined context for SQL generation)
    # ------------------------------------------------------------------

    async def get_context(
        self,
        query: str,
        database: Optional[str] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Assemble a rich context dict for a natural-language query.

        Returns schema matches, similar past queries, relevant patterns,
        and any feedback on similar questions.
        """
        schema_ctx = await self.search.search_all(
            query, database=database, top_k=top_k,
        )

        similar_queries = await self.episodes.search_similar_queries(
            query, top_k=top_k,
        )

        feedback = await self.episodes.get_feedback_for_query(
            query, limit=3,
        )

        return {
            **schema_ctx,
            "similar_queries": similar_queries,
            "feedback": feedback,
        }

    async def search_schema(
        self,
        query: str,
        top_k: int = 5,
        database: Optional[str] = None,
    ) -> SchemaSearchResult:
        """Convenience wrapper around SemanticSearchService.search_schema."""
        return await self.search.search_schema(query, top_k=top_k, database=database)

    # ------------------------------------------------------------------
    # statistics / health
    # ------------------------------------------------------------------

    async def get_stats(self) -> Dict[str, Any]:
        """Aggregate stats from both layers."""
        entity_stats = await self.entities.get_stats()
        episode_stats = await self.episodes.get_stats()
        return {
            "entities": entity_stats,
            "episodes": episode_stats,
        }

    async def close(self) -> None:
        await self._client.close()
