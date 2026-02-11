import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.knowledge.client import GraphitiClient

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 3
DEFAULT_SIMILARITY_THRESHOLD = 0.7

# Node labels supported by the generic vector search
_SEARCHABLE_LABELS = ("Table", "Column", "BusinessEntity", "QueryPattern")


@dataclass
class SearchResult:
    name: str
    label: str
    summary: str
    score: float
    attributes: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableContext:
    """Full context for a single table including columns, entities, and joins."""

    table: str
    database: str
    description: str
    partition_keys: List[str] = field(default_factory=list)
    columns: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    related_tables: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaSearchResult:
    tables: List[SearchResult] = field(default_factory=list)
    columns: List[SearchResult] = field(default_factory=list)
    entities: List[SearchResult] = field(default_factory=list)
    patterns: List[Dict[str, Any]] = field(default_factory=list)
    context: List[Dict[str, Any]] = field(default_factory=list)


class SemanticSearchService:
    """Unified semantic search over the graph knowledge base.

    Design principles
    -----------------
    * **One embedding per query** – the same vector is re-used across all
      label searches to avoid redundant API calls.
    * **Parallel graph queries** – independent Cypher queries run concurrently
      via ``asyncio.gather``.
    * **Rich context** – ``_get_table_context`` fetches columns, mapped
      business entities *and* join / foreign-key relationships in a single
      Cypher round-trip so the caller has everything needed for SQL generation.
    * **No duplication** – ``find_related_tables`` and ``search_similar_queries``
      that existed here as thin copies of ``EntityRegistry`` /
      ``EpisodeStore`` methods have been removed.  Callers should use
      those services directly.
    """

    def __init__(self, client: GraphitiClient):
        self._client = client

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @property
    def _driver(self):
        return self._client.graphiti.driver

    @property
    def _embedder(self):
        _ = self._client.graphiti          # ensure lazy init
        return self._client._embedder

    async def _execute(self, query: str, **kwargs) -> List[Dict]:
        result = await self._driver.execute_query(query, **kwargs)
        if result is None:
            return []
        records, _, _ = result
        return records or []

    async def _embed_query(self, query: str) -> List[float]:
        text = query.replace("\n", " ").strip()
        return await self._embedder.create(input_data=[text])

    @staticmethod
    def _parse_attrs(raw: Any) -> Dict:
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    # ------------------------------------------------------------------
    # generic vector search (single label)
    # ------------------------------------------------------------------

    async def _search_by_label(
        self,
        label: str,
        embedding: List[float],
        *,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        database: Optional[str] = None,
    ) -> List[SearchResult]:
        """Run a cosine-similarity search against nodes of *label*.

        The *embedding* is passed in so callers can compute it once and
        fan-out to multiple labels concurrently.
        """
        db_clause = ""
        params: Dict[str, Any] = dict(
            embedding=embedding, threshold=threshold, top_k=top_k,
        )
        if database:
            db_clause = "AND (n.name CONTAINS $database OR n.attributes CONTAINS $database)"
            params["database"] = database

        records = await self._execute(
            f"""
            MATCH (n:{label})
            WHERE n.embedding IS NOT NULL {db_clause}
            WITH n,
                 (2 - vec.cosineDistance(n.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            RETURN n.name AS name, n.summary AS summary,
                   n.attributes AS attributes, score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            **params,
        )
        return [
            SearchResult(
                name=r["name"],
                label=label,
                summary=r["summary"] or "",
                score=float(r["score"]),
                attributes=self._parse_attrs(r["attributes"]),
            )
            for r in records
        ]

    # ------------------------------------------------------------------
    # public per-label convenience methods (delegate to _search_by_label)
    # ------------------------------------------------------------------

    async def search_tables(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        database: Optional[str] = None,
    ) -> List[SearchResult]:
        embedding = await self._embed_query(query)
        return await self._search_by_label(
            "Table", embedding, top_k=top_k, threshold=threshold, database=database,
        )

    async def search_columns(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        database: Optional[str] = None,
    ) -> List[SearchResult]:
        embedding = await self._embed_query(query)
        return await self._search_by_label(
            "Column", embedding, top_k=top_k, threshold=threshold, database=database,
        )

    async def search_entities(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> List[SearchResult]:
        embedding = await self._embed_query(query)
        return await self._search_by_label(
            "BusinessEntity", embedding, top_k=top_k, threshold=threshold,
        )

    # ------------------------------------------------------------------
    # combined schema search (single embedding, parallel fan-out)
    # ------------------------------------------------------------------

    async def search_schema(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        database: Optional[str] = None,
    ) -> SchemaSearchResult:
        """Search tables, columns, entities and query-patterns in parallel
        using a *single* embedding.  Then enrich with full table context.
        """
        embedding = await self._embed_query(query)

        # fan-out: all four label searches run concurrently
        tables_task = self._search_by_label(
            "Table", embedding, top_k=top_k, threshold=threshold, database=database,
        )
        columns_task = self._search_by_label(
            "Column", embedding, top_k=top_k, threshold=threshold, database=database,
        )
        entities_task = self._search_by_label(
            "BusinessEntity", embedding, top_k=top_k, threshold=threshold,
        )
        patterns_task = self._search_by_label(
            "QueryPattern", embedding, top_k=top_k, threshold=threshold,
        )

        tables, columns, entities, pattern_results = await asyncio.gather(
            tables_task, columns_task, entities_task, patterns_task,
        )

        patterns = [
            {
                "name": p.name,
                "summary": p.summary,
                "score": p.score,
                "attributes": p.attributes,
            }
            for p in pattern_results
        ]

        # collect unique table names that need full context
        table_names = self._collect_table_names(tables, columns, entities)

        # fetch full context for every relevant table in parallel
        context_tasks = [self._get_table_context(name) for name in table_names]
        raw_contexts = await asyncio.gather(*context_tasks)
        context = [ctx.to_dict() for ctx in raw_contexts if ctx is not None]

        return SchemaSearchResult(
            tables=tables,
            columns=columns,
            entities=entities,
            patterns=patterns,
            context=context,
        )

    # ------------------------------------------------------------------
    # search_all  (main entry-point used by graph_tools / memory)
    # ------------------------------------------------------------------

    async def search_all(
        self,
        query: str,
        database: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> Dict[str, Any]:
        """Perform a combined search across all node types.

        Returns a dict with ``tables``, ``columns``, ``entities``,
        ``patterns`` and ``context`` keys.
        """
        result = await self.search_schema(
            query, top_k=top_k, threshold=threshold, database=database,
        )
        return {
            "tables": [r.to_dict() for r in result.tables],
            "columns": [r.to_dict() for r in result.columns],
            "entities": [r.to_dict() for r in result.entities],
            "patterns": result.patterns,
            "context": result.context,
        }

    # ------------------------------------------------------------------
    # table context (rich, single-query fetch)
    # ------------------------------------------------------------------

    async def _get_table_context(self, table_name: str) -> Optional[TableContext]:
        """Fetch full context for a table in **one** Cypher query:
        columns, mapped business entities, and join / FK relationships.
        """
        records = await self._execute(
            """
            MATCH (t:Table {name: $name})
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (e:BusinessEntity)-[:ENTITY_MAPPING]->(t)
            OPTIONAL MATCH (t)-[rel:JOIN|FOREIGN_KEY]-(related:Table)
            RETURN t.name        AS table_name,
                   t.summary     AS description,
                   t.attributes  AS table_attrs,
                   collect(DISTINCT {
                       name:       c.name,
                       summary:    c.summary,
                       attributes: c.attributes
                   }) AS columns,
                   collect(DISTINCT {
                       name:       e.name,
                       summary:    e.summary,
                       attributes: e.attributes
                   }) AS entities,
                   collect(DISTINCT {
                       name:         related.name,
                       relationship: type(rel),
                       attributes:   rel.attributes
                   }) AS relations
            """,
            name=table_name,
        )

        if not records:
            return None

        row = records[0]
        table_attrs = self._parse_attrs(row["table_attrs"])

        columns = []
        for col in row.get("columns", []):
            if not col.get("name"):
                continue
            col_attrs = self._parse_attrs(col.get("attributes"))
            columns.append({
                "name": col_attrs.get("column_name", col["name"]),
                "type": col_attrs.get("data_type", ""),
                "description": col.get("summary", "") or "",
                "is_primary_key": col_attrs.get("is_primary_key", False),
                "is_foreign_key": col_attrs.get("is_foreign_key", False),
                "is_partition": col_attrs.get("is_partition", False),
                "is_nullable": col_attrs.get("is_nullable", True),
            })

        entities = []
        for ent in row.get("entities", []):
            if not ent.get("name"):
                continue
            ent_attrs = self._parse_attrs(ent.get("attributes"))
            entities.append({
                "name": ent["name"],
                "domain": ent_attrs.get("domain", ""),
                "synonyms": ent_attrs.get("synonyms", []),
                "description": ent.get("summary", "") or "",
            })

        related_tables = []
        for rel in row.get("relations", []):
            if not rel.get("name"):
                continue
            rel_attrs = self._parse_attrs(rel.get("attributes"))
            related_tables.append({
                "table": rel["name"],
                "relationship": rel.get("relationship", "RELATED"),
                "join_type": rel_attrs.get("join_type"),
                "join_condition": rel_attrs.get("join_condition"),
            })

        return TableContext(
            table=table_attrs.get("table_name", row["table_name"]),
            database=table_attrs.get("database", ""),
            description=row["description"] or "",
            partition_keys=table_attrs.get("partition_keys", []),
            columns=columns,
            entities=entities,
            related_tables=related_tables,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_table_names(
        tables: List[SearchResult],
        columns: List[SearchResult],
        entities: List[SearchResult],
    ) -> List[str]:
        """Deduplicate table names from search hits across all categories."""
        seen: dict[str, None] = {}  # insertion-ordered set

        for t in tables:
            if t.name not in seen:
                seen[t.name] = None

        for c in columns:
            tbl = c.attributes.get("table_name", "")
            db = c.attributes.get("database", "")
            full = f"{db}.{tbl}" if db else tbl
            if full and full not in seen:
                seen[full] = None

        for e in entities:
            # entities can map to multiple tables via ENTITY_MAPPING;
            # the mapping is resolved inside _get_table_context, so we
            # don't need to add them here.
            pass

        return list(seen)
