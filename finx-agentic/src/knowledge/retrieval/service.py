"""SemanticSearchService — multi-level retrieval pipeline over the graph."""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.constants import DEFAULT_TOP_K, DEFAULT_SIMILARITY_THRESHOLD
from src.knowledge.retrieval.analyzer import QueryAnalyzer, QueryAnalysis
from src.knowledge.retrieval.reranker import SearchReranker, ScoredItem, RerankerWeights
from src.knowledge.retrieval.models import SearchResult, TableContext, SchemaSearchResult

logger = logging.getLogger(__name__)


class SemanticSearchService:
    """Unified semantic search over the graph knowledge base.

    Multi-level retrieval pipeline:
    1. Query Analysis — extract entities, intent, complexity, temporal context.
    2. Level 1 — Exact match on entity names / synonyms.
    3. Level 2 — Graph expansion (1-2 hops from L1 hits).
    4. Level 3 — Query pattern match by intent.
    5. Level 4 — Vector similarity search.
    6. Context enrichment — full table context.
    7. Intelligent reranking — weighted multi-signal scoring.
    8. Fallback strategies — relaxed search, domain discovery.
    """

    EARLY_STOP_SCORE = 0.90

    def __init__(self, client: GraphitiClient):
        self._client = client
        self._analyzer = QueryAnalyzer()
        self._reranker = SearchReranker(
            weights=RerankerWeights(),
            confidence_threshold=0.35,
            top_k=10,
        )

    @property
    def _driver(self):
        return self._client.graphiti.driver

    @property
    def _embedder(self):
        _ = self._client.graphiti
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

    # ══════════════════════════════════════════════════════════════════
    #  LEVEL 1 — Exact / Synonym Match
    # ══════════════════════════════════════════════════════════════════

    async def _level1_exact_match(
        self, terms: List[str], database: Optional[str] = None,
    ) -> List[ScoredItem]:
        if not terms:
            return []

        items: List[ScoredItem] = []

        for term in terms[:10]:
            db_filter = ""
            params: Dict[str, Any] = {"term": term}
            if database:
                db_filter = "AND (e.attributes CONTAINS $database OR e.name CONTAINS $database)"
                params["database"] = database

            records = await self._execute(
                f"""
                MATCH (e:BusinessEntity)
                WHERE (toLower(e.name) CONTAINS toLower($term)
                   OR e.attributes CONTAINS $term)
                {db_filter}
                RETURN e.name AS name, e.summary AS summary,
                       e.attributes AS attributes, labels(e) AS lbls
                LIMIT 5
                """,
                **params,
            )
            for r in records:
                items.append(ScoredItem(
                    name=r["name"], label="BusinessEntity",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=1.0, graph_relevance_score=1.0,
                    match_type="exact", hop_distance=0, source_level="level1",
                ))

            records = await self._execute(
                f"""
                MATCH (t:Table)
                WHERE toLower(t.name) CONTAINS toLower($term)
                {db_filter.replace('e.', 't.')}
                RETURN t.name AS name, t.summary AS summary,
                       t.attributes AS attributes
                LIMIT 5
                """,
                **params,
            )
            for r in records:
                items.append(ScoredItem(
                    name=r["name"], label="Table",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=1.0, graph_relevance_score=1.0,
                    match_type="exact", hop_distance=0, source_level="level1",
                ))

        return items

    # ══════════════════════════════════════════════════════════════════
    #  LEVEL 2 — Graph Expansion
    # ══════════════════════════════════════════════════════════════════

    async def _level2_graph_expansion(
        self, l1_items: List[ScoredItem], max_hops: int = 2,
    ) -> List[ScoredItem]:
        if not l1_items:
            return []

        entity_names = list({it.name for it in l1_items if it.label == "BusinessEntity"})[:5]
        table_names = list({it.name for it in l1_items if it.label == "Table"})[:5]
        items: List[ScoredItem] = []

        if entity_names:
            records = await self._execute(
                """
                MATCH (e:BusinessEntity)-[r1]->(hop1)
                WHERE e.name IN $names
                OPTIONAL MATCH (hop1)-[r2]->(hop2) WHERE hop2 <> e
                RETURN e.name AS source,
                       hop1.name AS hop1_name, labels(hop1) AS hop1_labels,
                       hop1.summary AS hop1_summary, hop1.attributes AS hop1_attrs,
                       type(r1) AS rel1,
                       hop2.name AS hop2_name, labels(hop2) AS hop2_labels,
                       hop2.summary AS hop2_summary, hop2.attributes AS hop2_attrs,
                       type(r2) AS rel2
                LIMIT 30
                """,
                names=entity_names,
            )
            for r in records:
                if r.get("hop1_name"):
                    label = (r.get("hop1_labels") or ["Unknown"])[0]
                    items.append(ScoredItem(
                        name=r["hop1_name"], label=label,
                        summary=r.get("hop1_summary") or "",
                        attributes=self._parse_attrs(r.get("hop1_attrs")),
                        text_match_score=SearchReranker.compute_text_match("graph_expansion"),
                        graph_relevance_score=SearchReranker.compute_graph_relevance(hop_distance=1),
                        match_type="graph_expansion", hop_distance=1, source_level="level2",
                    ))
                if r.get("hop2_name") and max_hops >= 2:
                    label = (r.get("hop2_labels") or ["Unknown"])[0]
                    items.append(ScoredItem(
                        name=r["hop2_name"], label=label,
                        summary=r.get("hop2_summary") or "",
                        attributes=self._parse_attrs(r.get("hop2_attrs")),
                        text_match_score=SearchReranker.compute_text_match("graph_expansion"),
                        graph_relevance_score=SearchReranker.compute_graph_relevance(hop_distance=2),
                        match_type="graph_expansion", hop_distance=2, source_level="level2",
                    ))

        if table_names:
            records = await self._execute(
                """
                MATCH (t:Table)-[r:JOIN|FOREIGN_KEY|BELONGS_TO_DOMAIN]-(related)
                WHERE t.name IN $names
                RETURN t.name AS source,
                       related.name AS related_name, labels(related) AS related_labels,
                       related.summary AS related_summary, related.attributes AS related_attrs,
                       type(r) AS rel_type
                LIMIT 20
                """,
                names=table_names,
            )
            for r in records:
                if r.get("related_name"):
                    label = (r.get("related_labels") or ["Unknown"])[0]
                    items.append(ScoredItem(
                        name=r["related_name"], label=label,
                        summary=r.get("related_summary") or "",
                        attributes=self._parse_attrs(r.get("related_attrs")),
                        text_match_score=SearchReranker.compute_text_match("graph_expansion"),
                        graph_relevance_score=SearchReranker.compute_graph_relevance(hop_distance=1),
                        match_type="graph_expansion", hop_distance=1, source_level="level2",
                    ))

        return items

    # ══════════════════════════════════════════════════════════════════
    #  LEVEL 3 — Query Pattern Match
    # ══════════════════════════════════════════════════════════════════

    async def _level3_pattern_match(self, analysis: QueryAnalysis) -> List[ScoredItem]:
        items: List[ScoredItem] = []
        records = await self._execute(
            """
            MATCH (qp:QueryPattern)
            WHERE qp.attributes CONTAINS $intent
            OPTIONAL MATCH (qp)-[:QUERY_USES_TABLE]->(t:Table)
            RETURN qp.name AS name, qp.summary AS summary,
                   qp.attributes AS attrs, collect(DISTINCT t.name) AS tables
            LIMIT 10
            """,
            intent=analysis.intent.value,
        )
        for r in records:
            attrs = self._parse_attrs(r.get("attrs"))
            items.append(ScoredItem(
                name=r["name"], label="QueryPattern",
                summary=r.get("summary") or "", attributes=attrs,
                text_match_score=0.7, graph_relevance_score=0.6,
                usage_frequency_score=SearchReranker.compute_usage_frequency(
                    frequency=attrs.get("frequency", 0),
                    success_rate=attrs.get("success_rate", 0.0),
                ),
                match_type="pattern", hop_distance=0, source_level="level3",
                context={"tables_involved": r.get("tables", [])},
            ))
        return items

    # ══════════════════════════════════════════════════════════════════
    #  LEVEL 4 — Vector Similarity
    # ══════════════════════════════════════════════════════════════════

    async def _level4_vector_search(
        self, embedding: List[float], *,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        database: Optional[str] = None,
    ) -> List[ScoredItem]:

        async def _vec_search(label: str) -> List[ScoredItem]:
            results = await self._search_by_label(
                label, embedding, top_k=top_k, threshold=threshold, database=database,
            )
            return [
                ScoredItem(
                    name=r.name, label=r.label,
                    summary=r.summary, attributes=r.attributes,
                    text_match_score=SearchReranker.compute_text_match("vector", r.score),
                    graph_relevance_score=SearchReranker.compute_graph_relevance(hop_distance=0),
                    match_type="vector", hop_distance=0, source_level="level4",
                )
                for r in results
            ]

        tables, columns, entities, patterns = await asyncio.gather(
            _vec_search("Table"),
            _vec_search("Column"),
            _vec_search("BusinessEntity"),
            _vec_search("QueryPattern"),
        )
        return tables + columns + entities + patterns

    # ══════════════════════════════════════════════════════════════════
    #  CONTEXT ENRICHMENT
    # ══════════════════════════════════════════════════════════════════

    async def _enrich_scored_items(
        self, items: List[ScoredItem], target_domain: Optional[str] = None,
    ) -> List[ScoredItem]:
        for item in items:
            attrs = item.attributes
            item.data_quality_score = SearchReranker.compute_data_quality(
                has_description=bool(item.summary),
                has_sample_values=bool(attrs.get("sample_values")),
                has_business_rules=bool(item.context.get("rules")),
                has_partition_keys=bool(attrs.get("partition_keys")),
                column_completeness=0.5,
            )
            item_domain = attrs.get("domain", "")
            same_domain = bool(target_domain and item_domain and target_domain.lower() == item_domain.lower())
            item.business_context_score = SearchReranker.compute_business_context(
                same_domain=same_domain, has_owner=bool(attrs.get("owner")),
            )

        table_items = [it for it in items if it.label == "Table"]
        if table_items:
            contexts = await asyncio.gather(
                *[self._get_table_context(it.name) for it in table_items]
            )
            for it, ctx in zip(table_items, contexts):
                if ctx is None:
                    continue
                it.context = ctx.to_dict()
                col_count = len(ctx.columns)
                described = sum(1 for c in ctx.columns if c.get("description"))
                it.data_quality_score = SearchReranker.compute_data_quality(
                    has_description=bool(ctx.description),
                    has_sample_values=False,
                    has_business_rules=bool(ctx.business_rules),
                    has_partition_keys=bool(ctx.partition_keys),
                    column_completeness=described / col_count if col_count else 0.0,
                )
                if ctx.domain and target_domain and ctx.domain.lower() == target_domain.lower():
                    it.business_context_score = SearchReranker.compute_business_context(same_domain=True)

        return items

    # ══════════════════════════════════════════════════════════════════
    #  FALLBACK STRATEGIES
    # ══════════════════════════════════════════════════════════════════

    async def _fallback_domain_discovery(self) -> List[Dict[str, Any]]:
        records = await self._execute(
            """
            MATCH (d:Domain)
            OPTIONAL MATCH (d)-[:CONTAINS_ENTITY]->(e:BusinessEntity)
            OPTIONAL MATCH (t:Table)-[:BELONGS_TO_DOMAIN]->(d)
            RETURN d.name AS domain, d.summary AS description,
                   count(DISTINCT e) AS entity_count, count(DISTINCT t) AS table_count,
                   collect(DISTINCT e.name)[0..5] AS sample_entities,
                   collect(DISTINCT t.name)[0..5] AS sample_tables
            ORDER BY table_count DESC LIMIT 10
            """,
        )
        return [
            {
                "domain": r["domain"],
                "description": r.get("description", ""),
                "entity_count": r.get("entity_count", 0),
                "table_count": r.get("table_count", 0),
                "sample_entities": r.get("sample_entities", []),
                "sample_tables": r.get("sample_tables", []),
            }
            for r in records if r.get("domain")
        ]

    async def _fallback_relaxed_search(
        self, embedding: List[float], database: Optional[str] = None,
    ) -> List[ScoredItem]:
        return await self._level4_vector_search(
            embedding, top_k=10, threshold=0.3, database=database,
        )

    async def _log_missing_query(self, query: str, attempted_terms: List[str]) -> None:
        try:
            await self._execute(
                """
                MERGE (mq:MissingQuery {text: $text})
                SET mq.timestamp = $ts,
                    mq.failed_entities = $terms,
                    mq.attempt_count = COALESCE(mq.attempt_count, 0) + 1
                """,
                text=query[:500], ts=time.time(), terms=json.dumps(attempted_terms),
            )
        except Exception:
            logger.debug("Could not log missing query: %s", query[:80])

    # ══════════════════════════════════════════════════════════════════
    #  GENERIC VECTOR SEARCH (single label)
    # ══════════════════════════════════════════════════════════════════

    async def _search_by_label(
        self, label: str, embedding: List[float], *,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        database: Optional[str] = None,
    ) -> List[SearchResult]:
        db_clause = ""
        params: Dict[str, Any] = dict(embedding=embedding, threshold=threshold, top_k=top_k)
        if database:
            db_clause = "AND (n.name CONTAINS $database OR n.attributes CONTAINS $database)"
            params["database"] = database

        records = await self._execute(
            f"""
            MATCH (n:{label})
            WHERE n.embedding IS NOT NULL {db_clause}
            WITH n, (2 - vec.cosineDistance(n.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            RETURN n.name AS name, n.summary AS summary, n.attributes AS attributes, score
            ORDER BY score DESC LIMIT $top_k
            """,
            **params,
        )
        return [
            SearchResult(
                name=r["name"], label=label, summary=r["summary"] or "",
                score=float(r["score"]), attributes=self._parse_attrs(r["attributes"]),
            )
            for r in records
        ]

    # ══════════════════════════════════════════════════════════════════
    #  PUBLIC PER-LABEL SEARCH
    # ══════════════════════════════════════════════════════════════════

    async def search_tables(
        self, query: str, top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD, database: Optional[str] = None,
    ) -> List[SearchResult]:
        embedding = await self._embed_query(query)
        return await self._search_by_label("Table", embedding, top_k=top_k, threshold=threshold, database=database)

    async def search_columns(
        self, query: str, top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD, database: Optional[str] = None,
    ) -> List[SearchResult]:
        embedding = await self._embed_query(query)
        return await self._search_by_label("Column", embedding, top_k=top_k, threshold=threshold, database=database)

    async def search_entities(
        self, query: str, top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> List[SearchResult]:
        embedding = await self._embed_query(query)
        return await self._search_by_label("BusinessEntity", embedding, top_k=top_k, threshold=threshold)

    # ══════════════════════════════════════════════════════════════════
    #  MAIN PIPELINE
    # ══════════════════════════════════════════════════════════════════

    async def search_schema(
        self, query: str, top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        database: Optional[str] = None,
    ) -> SchemaSearchResult:
        t0 = time.time()

        # Step 1: Query Analysis
        analysis = self._analyzer.analyze(query)
        db = database or analysis.database_hint
        search_terms = analysis.entities + analysis.key_business_terms

        # Step 2: Level 1 — Exact Match
        all_candidates: List[ScoredItem] = []
        l1_items = await self._level1_exact_match(search_terms, database=db)
        all_candidates.extend(l1_items)

        best_l1 = max((it.text_match_score for it in l1_items), default=0.0)
        skip_deeper = best_l1 >= self.EARLY_STOP_SCORE and len(l1_items) >= 3

        # Steps 3-5: Deeper levels (if needed)
        if not skip_deeper:
            embedding = await self._embed_query(query)
            l2_items, l3_items, l4_items = await asyncio.gather(
                self._level2_graph_expansion(l1_items),
                self._level3_pattern_match(analysis),
                self._level4_vector_search(embedding, top_k=top_k, threshold=threshold, database=db),
            )
            all_candidates.extend(l2_items)
            all_candidates.extend(l3_items)
            all_candidates.extend(l4_items)
        else:
            embedding = await self._embed_query(query)

        # Step 6: Enrich
        target_domain = next(
            (it.attributes.get("domain") for it in all_candidates if it.attributes.get("domain")),
            None,
        )
        all_candidates = await self._enrich_scored_items(all_candidates, target_domain=target_domain)

        # Step 7: Rerank
        ranked = self._reranker.rerank(all_candidates, threshold=0.20, top_k=top_k)

        # Step 8: Fallback
        fallback_domains: List[Dict[str, Any]] = []
        if not ranked:
            relaxed = await self._fallback_relaxed_search(embedding, database=db)
            if relaxed:
                relaxed = await self._enrich_scored_items(relaxed)
                ranked = self._reranker.rerank(relaxed, threshold=0.15, top_k=top_k)

            if not ranked:
                fallback_domains = await self._fallback_domain_discovery()

            await self._log_missing_query(query, search_terms)

        # Build result
        tables: List[SearchResult] = []
        columns: List[SearchResult] = []
        entities: List[SearchResult] = []
        patterns: List[Dict[str, Any]] = []

        for item in ranked:
            sr = SearchResult(
                name=item.name, label=item.label,
                summary=item.summary, score=item.final_score, attributes=item.attributes,
            )
            if item.label == "Table":
                tables.append(sr)
            elif item.label == "Column":
                columns.append(sr)
            elif item.label == "BusinessEntity":
                entities.append(sr)
            elif item.label == "QueryPattern":
                patterns.append({
                    "name": item.name, "summary": item.summary,
                    "score": item.final_score, "attributes": item.attributes,
                })

        # Fetch full context for top tables
        table_names = self._collect_table_names(tables, columns, entities)
        raw_contexts = await asyncio.gather(
            *[self._get_table_context(name) for name in table_names]
        )
        context = [ctx.to_dict() for ctx in raw_contexts if ctx is not None]

        elapsed_ms = round((time.time() - t0) * 1000)
        logger.debug("search_schema completed in %dms — tables=%d columns=%d entities=%d",
                      elapsed_ms, len(tables), len(columns), len(entities))

        return SchemaSearchResult(
            tables=tables, columns=columns, entities=entities,
            patterns=patterns, context=context,
            ranked_results=[it.to_dict() for it in ranked],
            query_analysis={
                "intent": analysis.intent.value,
                "complexity": analysis.complexity.value,
                "entities": analysis.entities,
                "temporal_context": analysis.temporal_context,
                "aggregation_functions": analysis.aggregation_functions,
                "business_terms": analysis.key_business_terms,
                "database_hint": analysis.database_hint,
                "is_vietnamese": analysis.is_vietnamese,
            },
            search_metadata={
                "elapsed_ms": elapsed_ms,
                "levels_executed": "L1" if skip_deeper else "L1-L4",
                "total_candidates": len(all_candidates),
                "after_rerank": len(ranked),
                "early_stopped": skip_deeper,
                "fallback_used": bool(fallback_domains),
                "fallback_domains": fallback_domains,
            },
        )

    # ══════════════════════════════════════════════════════════════════
    #  SEARCH ALL
    # ══════════════════════════════════════════════════════════════════

    async def search_all(
        self, query: str, database: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K, threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> Dict[str, Any]:
        result = await self.search_schema(query, top_k=top_k, threshold=threshold, database=database)
        return {
            "tables": [r.to_dict() for r in result.tables],
            "columns": [r.to_dict() for r in result.columns],
            "entities": [r.to_dict() for r in result.entities],
            "patterns": result.patterns,
            "context": result.context,
            "ranked_results": result.ranked_results,
            "query_analysis": result.query_analysis,
            "search_metadata": result.search_metadata,
        }

    # ══════════════════════════════════════════════════════════════════
    #  TABLE CONTEXT
    # ══════════════════════════════════════════════════════════════════

    async def _get_table_context(self, table_name: str) -> Optional[TableContext]:
        records = await self._execute(
            """
            MATCH (t:Table {name: $name})
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (e:BusinessEntity)-[:ENTITY_MAPPING]->(t)
            OPTIONAL MATCH (t)-[rel:JOIN|FOREIGN_KEY]-(related:Table)
            OPTIONAL MATCH (t)-[:BELONGS_TO_DOMAIN]->(d:Domain)
            OPTIONAL MATCH (rule:BusinessRule)-[:APPLIES_TO]->(t)
            OPTIONAL MATCH (c)-[:HAS_CODESET]->(cs:CodeSet)
            RETURN t.name        AS table_name,
                   t.summary     AS description,
                   t.attributes  AS table_attrs,
                   collect(DISTINCT {name: c.name, summary: c.summary, attributes: c.attributes}) AS columns,
                   collect(DISTINCT {name: e.name, summary: e.summary, attributes: e.attributes}) AS entities,
                   collect(DISTINCT {name: related.name, relationship: type(rel), attributes: rel.attributes}) AS relations,
                   d.name AS domain_name,
                   collect(DISTINCT {name: rule.name, summary: rule.summary, attributes: rule.attributes}) AS rules,
                   collect(DISTINCT {name: cs.name, summary: cs.summary, attributes: cs.attributes}) AS codesets
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

        entities_list = []
        for ent in row.get("entities", []):
            if not ent.get("name"):
                continue
            ent_attrs = self._parse_attrs(ent.get("attributes"))
            entities_list.append({
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

        business_rules = []
        for rule in row.get("rules", []):
            if not rule.get("name"):
                continue
            rule_attrs = self._parse_attrs(rule.get("attributes"))
            business_rules.append({
                "name": rule["name"],
                "description": rule.get("summary", "") or "",
                "rule_type": rule_attrs.get("rule_type", ""),
                "expression": rule_attrs.get("expression", ""),
            })

        codesets = []
        for cs in row.get("codesets", []):
            if not cs.get("name"):
                continue
            cs_attrs = self._parse_attrs(cs.get("attributes"))
            codesets.append({
                "name": cs["name"],
                "description": cs.get("summary", "") or "",
                "codes": cs_attrs.get("codes", {}),
                "column_name": cs_attrs.get("column_name", ""),
            })

        return TableContext(
            table=table_attrs.get("table_name", row["table_name"]),
            database=table_attrs.get("database", ""),
            description=row["description"] or "",
            partition_keys=table_attrs.get("partition_keys", []),
            columns=columns,
            entities=entities_list,
            related_tables=related_tables,
            domain=row.get("domain_name"),
            business_rules=business_rules,
            codesets=codesets,
        )

    @staticmethod
    def _collect_table_names(
        tables: List[SearchResult],
        columns: List[SearchResult],
        entities: List[SearchResult],
    ) -> List[str]:
        seen: dict[str, None] = {}
        for t in tables:
            if t.name not in seen:
                seen[t.name] = None
        for c in columns:
            tbl = c.attributes.get("table_name", "")
            db = c.attributes.get("database", "")
            full = f"{db}.{tbl}" if db else tbl
            if full and full not in seen:
                seen[full] = None
        return list(seen)
