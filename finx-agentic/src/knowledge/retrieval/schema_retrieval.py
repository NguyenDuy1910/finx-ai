"""Hierarchical schema retrieval: domain -> synonym -> table -> column -> pattern."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.constants import DEFAULT_TOP_K, DEFAULT_SIMILARITY_THRESHOLD
from src.knowledge.retrieval.reranker import (
    SearchReranker,
    ScoredItem,
    weights_for_intent,
)
from src.knowledge.retrieval import SearchResult, TableContext, SchemaSearchResult
from src.core.log_tracker import log_tracker

logger = logging.getLogger(__name__)


@log_tracker(level="DEBUG", log_args=True, log_result=True, max_str_len=5000)
class SchemaRetrievalService:
    """Five-layer hierarchical search with score propagation across layers."""

    def __init__(self, client: GraphitiClient):
        self._client = client

    @property
    def _driver(self):
        return self._client.graphiti.driver

    @property
    def _embedder(self):
        _ = self._client.graphiti
        return self._client._embedder

    # -- low-level helpers --------------------------------------------------------

    async def _execute(self, cypher: str, **kwargs) -> List[Dict]:
        """Run a Cypher query and return the list of record dicts."""
        result = await self._driver.execute_query(cypher, **kwargs)
        if result is None:
            return []
        records, _, _ = result
        return records or []

    async def _embed_query(self, query: str) -> List[float]:
        """Embed a natural-language query string."""
        text = query.replace("\n", " ").strip()
        return await self._embedder.create(input_data=[text])

    @staticmethod
    def _parse_attrs(raw: Any) -> Dict:
        """Parse JSON attributes stored as string on graph nodes."""
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    async def _vector_search_label(
        self,
        label: str,
        embedding: List[float],
        *,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        exclude_names: Optional[Set[str]] = None,
    ) -> List[SearchResult]:
        """Cosine-similarity search on a single node label."""
        params: Dict[str, Any] = dict(
            embedding=embedding, threshold=threshold, top_k=top_k,
        )

        records = await self._execute(
            f"""
            MATCH (n:{label})
            WHERE n.embedding IS NOT NULL
            WITH n,
                 (2 - vec.cosineDistance(n.embedding, vecf32($embedding))) / 2 AS score
            WHERE score >= $threshold
            RETURN n.name AS name, n.summary AS summary,
                   n.attributes AS attributes, score
            ORDER BY score DESC LIMIT $top_k
            """,
            **params,
        )
        results: List[SearchResult] = []
        skip = exclude_names or set()
        for r in records:
            if r["name"] in skip:
                continue
            results.append(SearchResult(
                name=r["name"], label=label, summary=r["summary"] or "",
                score=float(r["score"]),
                attributes=self._parse_attrs(r["attributes"]),
            ))
        return results

    # -- layer 1: domain resolution -----------------------------------------------

    async def _layer1_domain_resolution(
        self,
        embedding: List[float],
        domain_hint: Optional[str] = None,
    ) -> List[ScoredItem]:
        """Resolve which business domains are relevant via hint anchor + vector search + neighborhood."""
        items: List[ScoredItem] = []
        seen: Set[str] = set()

        # 1a: if caller already knows the domain, anchor on it directly
        if domain_hint:
            records = await self._execute(
                """
                MATCH (d:Domain)
                WHERE toLower(d.name) = toLower($name)
                RETURN d.name AS name, d.summary AS summary,
                       d.attributes AS attributes
                LIMIT 1
                """,
                name=domain_hint,
            )
            for r in records:
                seen.add(r["name"])
                items.append(ScoredItem(
                    name=r["name"], label="Domain",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=1.0,
                    graph_relevance_score=1.0,
                    match_type="exact", hop_distance=0,
                    source_layer="layer1_domain",
                ))

        # 1b: vector search on Domain nodes
        if embedding:
            vec_results = await self._vector_search_label(
                "Domain", embedding, top_k=5, threshold=0.45,
            )
            for r in vec_results:
                if r.name in seen:
                    continue
                seen.add(r.name)
                items.append(ScoredItem(
                    name=r.name, label="Domain",
                    summary=r.summary, attributes=r.attributes,
                    text_match_score=SearchReranker.score_text_match("vector", r.score),
                    graph_relevance_score=SearchReranker.score_graph_relevance(0),
                    match_type="vector", hop_distance=0,
                    source_layer="layer1_domain",
                ))

        # 1c: explore neighborhood — find related domains via shared tables/entities
        anchor_domains = [it.name for it in items][:3]
        if anchor_domains:
            records = await self._execute(
                """
                MATCH (d:Domain)<-[:BELONGS_TO_DOMAIN]-(t:Table)-[:BELONGS_TO_DOMAIN]->(neighbor:Domain)
                WHERE d.name IN $domains AND NOT neighbor.name IN $domains
                RETURN DISTINCT neighbor.name AS name, neighbor.summary AS summary,
                       neighbor.attributes AS attributes, d.name AS via_domain
                LIMIT 5
                """,
                domains=anchor_domains,
            )
            for r in records:
                if r["name"] in seen:
                    continue
                seen.add(r["name"])
                items.append(ScoredItem(
                    name=r["name"], label="Domain",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=0.3,
                    graph_relevance_score=SearchReranker.score_graph_relevance(1),
                    match_type="graph_expansion", hop_distance=1,
                    source_layer="layer1_domain",
                    context={"via_domain": r.get("via_domain")},
                ))

        return items

    # -- layer 2: entity & synonym resolution (embedding + neighborhood) --------

    async def _layer2_entity_resolution(
        self,
        embedding: List[float],
        domain_items: List[ScoredItem],
    ) -> List[ScoredItem]:
        """Resolve business entities via vector search + graph neighborhood exploration."""
        items: List[ScoredItem] = []
        seen: Set[str] = set()

        # 2a: vector search on BusinessEntity
        if embedding:
            vec_results = await self._vector_search_label(
                "BusinessEntity", embedding, top_k=8, threshold=0.45,
            )
            for r in vec_results:
                seen.add(r.name)
                items.append(ScoredItem(
                    name=r.name, label="BusinessEntity",
                    summary=r.summary, attributes=r.attributes,
                    text_match_score=SearchReranker.score_text_match("vector", r.score),
                    graph_relevance_score=SearchReranker.score_graph_relevance(0),
                    match_type="vector", hop_distance=0,
                    source_layer="layer2_entity",
                ))

        # 2b: explore SYNONYM edges from matched entities → discover related nodes
        entity_names = [it.name for it in items][:5]
        if entity_names:
            syn_records = await self._execute(
                """
                MATCH (e:BusinessEntity)-[s:SYNONYM]-(neighbor)
                WHERE e.name IN $names AND NOT neighbor.name IN $names
                RETURN DISTINCT
                       neighbor.name AS name, labels(neighbor) AS labels,
                       neighbor.summary AS summary, neighbor.attributes AS attrs,
                       s.confidence AS confidence, e.name AS via_entity
                LIMIT 15
                """,
                names=entity_names,
            )
            for r in syn_records:
                name = r.get("name")
                if not name or name in seen:
                    continue
                seen.add(name)
                conf = float(r.get("confidence") or 1.0)
                lbls = r.get("labels") or ["BusinessEntity"]
                items.append(ScoredItem(
                    name=name, label=lbls[0],
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attrs")),
                    text_match_score=SearchReranker.score_text_match("synonym") * conf,
                    graph_relevance_score=SearchReranker.score_graph_relevance(1),
                    match_type="synonym", hop_distance=1,
                    source_layer="layer2_entity",
                    context={"via_entity": r.get("via_entity")},
                ))

        # 2c: explore entities connected to matched domains
        domain_names = [it.name for it in domain_items if it.label == "Domain"][:3]
        if domain_names:
            records = await self._execute(
                """
                MATCH (d:Domain)-[:CONTAINS_ENTITY]-(e:BusinessEntity)
                WHERE d.name IN $domains AND NOT e.name IN $seen
                RETURN DISTINCT e.name AS name, e.summary AS summary,
                       e.attributes AS attributes, d.name AS via_domain
                LIMIT 10
                """,
                domains=domain_names, seen=list(seen),
            )
            for r in records:
                if r["name"] in seen:
                    continue
                seen.add(r["name"])
                items.append(ScoredItem(
                    name=r["name"], label="BusinessEntity",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=0.4,
                    graph_relevance_score=SearchReranker.score_graph_relevance(1),
                    match_type="graph_expansion", hop_distance=1,
                    source_layer="layer2_entity",
                    context={"via_domain": r.get("via_domain")},
                ))

        return items

    # -- layer 3: table discovery (embedding + graph neighborhood) ---------------

    async def _layer3_table_discovery(
        self,
        embedding: List[float],
        entity_items: List[ScoredItem],
        domain_items: List[ScoredItem],
        *,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> List[ScoredItem]:
        """Find tables via vector search, entity mapping, and graph neighborhood."""
        items: List[ScoredItem] = []
        found_names: Set[str] = set()

        # 3a: vector search on Table nodes
        if embedding:
            vec_results = await self._vector_search_label(
                "Table", embedding,
                top_k=max(top_k, 8), threshold=threshold,
            )
            for r in vec_results:
                found_names.add(r.name)
                items.append(ScoredItem(
                    name=r.name, label="Table",
                    summary=r.summary, attributes=r.attributes,
                    text_match_score=SearchReranker.score_text_match("vector", r.score),
                    graph_relevance_score=SearchReranker.score_graph_relevance(0),
                    match_type="vector", hop_distance=0,
                    source_layer="layer3_table",
                ))

        # 3b: tables linked to matched entities via ENTITY_MAPPING
        entity_names = [
            it.name for it in entity_items if it.label == "BusinessEntity"
        ][:8]
        if entity_names:
            records = await self._execute(
                """
                MATCH (e:BusinessEntity)-[:ENTITY_MAPPING]->(t:Table)
                WHERE e.name IN $names
                RETURN DISTINCT t.name AS name, t.summary AS summary,
                       t.attributes AS attributes, e.name AS via_entity
                LIMIT 20
                """,
                names=entity_names,
            )
            for r in records:
                if r["name"] in found_names:
                    continue
                found_names.add(r["name"])
                items.append(ScoredItem(
                    name=r["name"], label="Table",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=SearchReranker.score_text_match("graph_expansion"),
                    graph_relevance_score=SearchReranker.score_graph_relevance(1),
                    match_type="graph_expansion", hop_distance=1,
                    source_layer="layer3_table",
                    context={"via_entity": r.get("via_entity")},
                ))

        # 3c: tables belonging to matched domains
        domain_names = [it.name for it in domain_items if it.label == "Domain"][:3]
        if domain_names:
            records = await self._execute(
                """
                MATCH (d:Domain)<-[:BELONGS_TO_DOMAIN]-(t:Table)
                WHERE d.name IN $domains AND NOT t.name IN $found
                RETURN DISTINCT t.name AS name, t.summary AS summary,
                       t.attributes AS attributes, d.name AS via_domain
                LIMIT 15
                """,
                domains=domain_names, found=list(found_names),
            )
            for r in records:
                if r["name"] in found_names:
                    continue
                found_names.add(r["name"])
                items.append(ScoredItem(
                    name=r["name"], label="Table",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=0.4,
                    graph_relevance_score=SearchReranker.score_graph_relevance(1),
                    match_type="graph_expansion", hop_distance=1,
                    source_layer="layer3_table",
                    context={"via_domain": r.get("via_domain")},
                ))

        # 3d: neighborhood expansion — JOIN / FK from already-found tables
        anchor_tables = list(found_names)[:8]
        if anchor_tables:
            records = await self._execute(
                """
                MATCH (t:Table)-[r:JOIN|FOREIGN_KEY]-(neighbor:Table)
                WHERE t.name IN $names AND NOT neighbor.name IN $names
                RETURN DISTINCT
                       neighbor.name AS name,
                       neighbor.summary AS summary,
                       neighbor.attributes AS attributes,
                       type(r) AS rel_type, t.name AS via_table
                LIMIT 20
                """,
                names=anchor_tables,
            )
            for r in records:
                name = r.get("name")
                if not name or name in found_names:
                    continue
                found_names.add(name)
                items.append(ScoredItem(
                    name=name, label="Table",
                    summary=r.get("summary") or "",
                    attributes=self._parse_attrs(r.get("attributes")),
                    text_match_score=SearchReranker.score_text_match("graph_expansion"),
                    graph_relevance_score=SearchReranker.score_graph_relevance(1),
                    match_type="graph_expansion", hop_distance=1,
                    source_layer="layer3_table",
                    context={"rel_type": r.get("rel_type"), "via_table": r.get("via_table")},
                ))

        return items

    # -- layer 4: column refinement -----------------------------------------------

    async def _layer4_column_refinement(
        self,
        embedding: List[float],
        table_items: List[ScoredItem],
        *,
        column_hints: Optional[List[str]] = None,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> List[ScoredItem]:
        """Refine results at column level using hints and vector search."""
        items: List[ScoredItem] = []
        found_names: Set[str] = set()

        # 4a: if we have column hints, match them on known tables
        hint_lower = {h.lower() for h in (column_hints or [])}
        if hint_lower:
            table_names = [it.name for it in table_items if it.label == "Table"][:10]
            if table_names:
                records = await self._execute(
                    """
                    MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
                    WHERE t.name IN $tables
                    RETURN c.name AS name, c.summary AS summary,
                           c.attributes AS attributes, t.name AS table_name
                    """,
                    tables=table_names,
                )
                for r in records:
                    col_attrs = self._parse_attrs(r.get("attributes"))
                    col_name = col_attrs.get("column_name", r["name"]).lower()
                    if col_name not in hint_lower:
                        continue
                    if r["name"] in found_names:
                        continue
                    found_names.add(r["name"])
                    col_attrs["table_name"] = r.get("table_name", "")
                    items.append(ScoredItem(
                        name=r["name"], label="Column",
                        summary=r.get("summary") or "",
                        attributes=col_attrs,
                        text_match_score=1.0,
                        graph_relevance_score=SearchReranker.score_graph_relevance(0),
                        match_type="exact", hop_distance=0,
                        source_layer="layer4_column",
                    ))

        # 4b: vector search for columns
        if embedding:
            vec_results = await self._vector_search_label(
                "Column", embedding,
                top_k=top_k, threshold=threshold,
                exclude_names=found_names,
            )
            for r in vec_results:
                items.append(ScoredItem(
                    name=r.name, label="Column",
                    summary=r.summary, attributes=r.attributes,
                    text_match_score=SearchReranker.score_text_match("vector", r.score),
                    graph_relevance_score=SearchReranker.score_graph_relevance(0),
                    match_type="vector", hop_distance=0,
                    source_layer="layer4_column",
                ))

        return items

    # -- layer 5: pattern & history (vector-based) --------------------------------

    async def _layer5_pattern_history(
        self,
        embedding: List[float],
    ) -> List[ScoredItem]:
        """Match against saved QueryPattern nodes via vector similarity."""
        items: List[ScoredItem] = []

        if not embedding:
            return items

        # vector search on QueryPattern
        vec_results = await self._vector_search_label(
            "QueryPattern", embedding, top_k=5, threshold=0.45,
        )
        for r in vec_results:
            attrs = r.attributes
            # resolve tables linked to this pattern
            table_records = await self._execute(
                """
                MATCH (qp:QueryPattern {name: $name})-[:QUERY_USES_TABLE]->(t:Table)
                RETURN collect(DISTINCT t.name) AS tables
                """,
                name=r.name,
            )
            tables_involved = table_records[0].get("tables", []) if table_records else []
            items.append(ScoredItem(
                name=r.name, label="QueryPattern",
                summary=r.summary, attributes=attrs,
                text_match_score=SearchReranker.score_text_match("vector", r.score),
                graph_relevance_score=0.4,
                usage_frequency_score=SearchReranker.score_usage_frequency(
                    frequency=attrs.get("frequency", 0),
                    success_rate=attrs.get("success_rate", 0.0),
                ),
                match_type="vector", hop_distance=0,
                source_layer="layer5_pattern",
                context={"tables_involved": tables_involved},
            ))

        return items

    # -- enrichment ---------------------------------------------------------------

    async def _enrich_table_items(
        self,
        items: List[ScoredItem],
        target_domain: Optional[str] = None,
        column_hints: Optional[List[str]] = None,
    ) -> None:
        """Populate data_quality and business_context scores for Table items."""
        col_hints_lower = {c.lower() for c in (column_hints or [])}
        table_items = [it for it in items if it.label == "Table"]
        if not table_items:
            return

        contexts = await asyncio.gather(
            *[self._get_table_context(it.name) for it in table_items]
        )
        for item, ctx in zip(table_items, contexts):
            if ctx is None:
                continue
            item.context = ctx.to_dict()
            col_count = len(ctx.columns)
            described = sum(1 for c in ctx.columns if c.get("description"))
            item.data_quality_score = SearchReranker.score_data_quality(
                has_description=bool(ctx.description),
                has_sample_values=False,
                has_business_rules=bool(ctx.business_rules),
                has_partition_keys=bool(ctx.partition_keys),
                column_completeness=described / col_count if col_count else 0.0,
            )
            same = bool(
                target_domain and ctx.domain
                and ctx.domain.lower() == target_domain.lower()
            )
            item.business_context_score = SearchReranker.score_business_context(
                same_domain=same,
            )
            # boost if column hints match columns in this table
            if col_hints_lower and ctx.columns:
                matched = sum(
                    1 for c in ctx.columns
                    if c.get("name", "").lower() in col_hints_lower
                )
                if matched:
                    ratio = min(1.0, matched / len(col_hints_lower))
                    item.text_match_score = min(
                        1.0, item.text_match_score + 0.3 * ratio,
                    )

    # -- fallback -----------------------------------------------------------------

    async def _fallback_relaxed_vector(
        self,
        embedding: List[float],
    ) -> List[ScoredItem]:
        """Last-resort vector search with a low threshold."""
        items: List[ScoredItem] = []
        for label in ("Table", "Column", "BusinessEntity"):
            results = await self._vector_search_label(
                label, embedding, top_k=5, threshold=0.3,
            )
            for r in results:
                items.append(ScoredItem(
                    name=r.name, label=r.label,
                    summary=r.summary, attributes=r.attributes,
                    text_match_score=SearchReranker.score_text_match("vector", r.score),
                    graph_relevance_score=SearchReranker.score_graph_relevance(0),
                    match_type="vector", hop_distance=0,
                    source_layer="fallback",
                ))
        return items

    async def _log_missing_query(
        self, query: str, context_hints: List[str],
    ) -> None:
        """Record a query that produced no results for future analysis."""
        try:
            await self._execute(
                """
                MERGE (mq:MissingQuery {text: $text})
                SET mq.timestamp = $ts,
                    mq.context_hints = $hints,
                    mq.attempt_count = COALESCE(mq.attempt_count, 0) + 1
                """,
                text=query[:500], ts=time.time(),
                hints=json.dumps(context_hints),
            )
        except Exception:
            logger.debug("Could not log missing query: %s", query[:80])

    # -- smart early stop ---------------------------------------------------------

    @staticmethod
    def _should_early_stop(items: List[ScoredItem], score_threshold: float = 0.90) -> bool:
        """Check if L3 table results are precise enough to skip deeper layers."""
        table_items = [it for it in items if it.label == "Table"]
        if len(table_items) < 3:
            return False
        best = max(it.text_match_score for it in table_items)
        if best < score_threshold:
            return False
        # verify results are concentrated (not scattered across many domains)
        domains = {it.attributes.get("domain") for it in table_items} - {None, ""}
        return len(domains) <= 2

    # -- public helpers -----------------------------------------------------------

    async def discover_domains(self) -> List[Dict]:
        """List all business domains with their tables and entities."""
        rows = await self._execute(
            """
            MATCH (d:Domain)
            OPTIONAL MATCH (d)-[:BELONGS_TO_DOMAIN]-(t:Table)
            OPTIONAL MATCH (d)-[:CONTAINS_ENTITY]-(e:BusinessEntity)
            RETURN d.name AS domain,
                   COALESCE(d.summary, '') AS summary,
                   COLLECT(DISTINCT t.name) AS tables,
                   COLLECT(DISTINCT e.name) AS entities
            ORDER BY domain
            """,
        )
        return [dict(r) for r in rows]

    # -- main entry point ---------------------------------------------------------

    async def schema_retrieval(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        entities: Optional[List[str]] = None,
        intent: Optional[str] = None,
        domain: Optional[str] = None,
        business_terms: Optional[List[str]] = None,
        column_hints: Optional[List[str]] = None,
        weight_overrides: Optional[Dict[str, float]] = None,
        include_patterns: bool = True,
        include_context: bool = True,
    ) -> SchemaSearchResult:
        """Orchestrate the five-layer hierarchical search pipeline.

        Strategy: embedding-first + graph neighborhood exploration.
        No keyword ``CONTAINS`` searches — all discovery is via vector
        similarity and graph edge traversal.
        """
        t0 = time.time()

        # select reranker weights based on intent, with optional LLM overrides
        reranker = SearchReranker(
            weights=weights_for_intent(intent, weight_overrides=weight_overrides),
            confidence_threshold=0.20,
            top_k=top_k,
        )

        # embed query once, reuse across all layers
        embedding = await self._embed_query(query)

        # -- layer 1: domain resolution (vector + neighborhood) --
        l1_items = await self._layer1_domain_resolution(
            embedding, domain_hint=domain,
        )
        domain_scores: Dict[str, float] = {
            it.name: it.text_match_score
            for it in l1_items if it.label == "Domain"
        }
        resolved_domain = domain or next(
            (it.name for it in l1_items if it.label == "Domain"), None,
        )

        # -- layer 2: entity resolution (vector + synonym edges + domain neighborhood) --
        l2_items = await self._layer2_entity_resolution(
            embedding, l1_items,
        )

        # -- layer 3: table discovery (vector + entity mapping + domain + JOIN/FK neighborhood) --
        l3_items = await self._layer3_table_discovery(
            embedding, l2_items, l1_items,
            top_k=top_k, threshold=threshold,
        )

        # check early stop before deeper layers
        early_stopped = self._should_early_stop(l3_items)

        # -- layer 4: column refinement (skip if early stop and no hints) --
        l4_items: List[ScoredItem] = []
        if not early_stopped or column_hints:
            l4_items = await self._layer4_column_refinement(
                embedding, l3_items,
                column_hints=column_hints,
                top_k=top_k, threshold=threshold,
            )

        # -- layer 5: pattern & history (skip if early stop or disabled) --
        l5_items: List[ScoredItem] = []
        if include_patterns and not early_stopped:
            l5_items = await self._layer5_pattern_history(embedding)

        # -- merge all candidates --
        all_candidates = l1_items + l2_items + l3_items + l4_items + l5_items

        # -- enrich table items with data_quality / business_context --
        await self._enrich_table_items(
            all_candidates,
            target_domain=resolved_domain,
            column_hints=column_hints,
        )

        # -- hierarchical score propagation --
        table_scores: Dict[str, float] = {
            it.name: it.text_match_score
            for it in all_candidates if it.label == "Table"
        }
        SearchReranker.propagate_scores(
            all_candidates, domain_scores, table_scores,
        )

        # -- rerank --
        ranked = reranker.rerank(all_candidates, threshold=0.20, top_k=top_k)

        # -- fallback if nothing survived --
        fallback_used = False
        if not ranked:
            fallback_items = await self._fallback_relaxed_vector(
                embedding,
            )
            if fallback_items:
                await self._enrich_table_items(
                    fallback_items, target_domain=resolved_domain,
                    column_hints=column_hints,
                )
                ranked = reranker.rerank(
                    fallback_items, threshold=0.15, top_k=top_k,
                )
            if not ranked:
                await self._log_missing_query(query, entities or [])
            fallback_used = True

        # -- categorize ranked results --
        tables: List[SearchResult] = []
        columns: List[SearchResult] = []
        entities_out: List[SearchResult] = []
        patterns: List[Dict[str, Any]] = []

        for item in ranked:
            sr = SearchResult(
                name=item.name, label=item.label,
                summary=item.summary, score=item.final_score,
                attributes=item.attributes,
            )
            if item.label == "Table":
                tables.append(sr)
            elif item.label == "Column":
                columns.append(sr)
            elif item.label == "BusinessEntity":
                entities_out.append(sr)
            elif item.label == "QueryPattern":
                patterns.append({
                    "name": item.name, "summary": item.summary,
                    "score": item.final_score,
                    "attributes": item.attributes,
                })

        # -- fetch full table context for top tables --
        context: List[Dict[str, Any]] = []
        if include_context:
            table_names = self._collect_table_names(tables, columns, entities_out)
            raw = await asyncio.gather(
                *[self._get_table_context(n) for n in table_names]
            )
            context = [c.to_dict() for c in raw if c is not None]

        # -- build layer execution metadata --
        layers = ["L1_domain", "L2_entity", "L3_table"]
        if l4_items:
            layers.append("L4_column")
        if l5_items:
            layers.append("L5_pattern")

        elapsed_ms = round((time.time() - t0) * 1000)
        logger.debug(
            "schema_retrieval completed in %dms, "
            "tables=%d columns=%d entities=%d",
            elapsed_ms, len(tables), len(columns), len(entities_out),
        )

        return SchemaSearchResult(
            tables=tables, columns=columns, entities=entities_out,
            patterns=patterns, context=context,
            ranked_results=[it.to_dict() for it in ranked],
            query_analysis={
                "query": query,
                "intent": intent,
                "domain": resolved_domain,
                "column_hints": column_hints or [],
            },
            search_metadata={
                "elapsed_ms": elapsed_ms,
                "layers_executed": "-".join(layers),
                "total_candidates": len(all_candidates),
                "after_rerank": len(ranked),
                "early_stopped": early_stopped,
                "fallback_used": fallback_used,
                "domain_scores": {
                    k: round(v, 3) for k, v in domain_scores.items()
                },
            },
        )

    # -- table context assembly ---------------------------------------------------

    async def _get_table_context(
        self, table_name: str,
    ) -> Optional[TableContext]:
        """Fetch full context for a table including columns, joins, rules, codesets."""
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
                   collect(DISTINCT {
                       name: c.name, summary: c.summary,
                       attributes: c.attributes
                   }) AS columns,
                   collect(DISTINCT {
                       name: e.name, summary: e.summary,
                       attributes: e.attributes
                   }) AS entities,
                   collect(DISTINCT {
                       name: related.name, relationship: type(rel),
                       attributes: rel.attributes
                   }) AS relations,
                   d.name AS domain_name,
                   collect(DISTINCT {
                       name: rule.name, summary: rule.summary,
                       attributes: rule.attributes
                   }) AS rules,
                   collect(DISTINCT {
                       name: cs.name, summary: cs.summary,
                       attributes: cs.attributes
                   }) AS codesets
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
            ca = self._parse_attrs(col.get("attributes"))
            columns.append({
                "name": ca.get("column_name", col["name"]),
                "type": ca.get("data_type", ""),
                "description": col.get("summary", "") or "",
                "is_primary_key": ca.get("is_primary_key", False),
                "is_foreign_key": ca.get("is_foreign_key", False),
                "is_partition": ca.get("is_partition", False),
                "is_nullable": ca.get("is_nullable", True),
            })

        entities_list = []
        for ent in row.get("entities", []):
            if not ent.get("name"):
                continue
            ea = self._parse_attrs(ent.get("attributes"))
            entities_list.append({
                "name": ent["name"],
                "domain": ea.get("domain", ""),
                "synonyms": ea.get("synonyms", []),
                "description": ent.get("summary", "") or "",
            })

        related_tables = []
        for rel in row.get("relations", []):
            if not rel.get("name"):
                continue
            ra = self._parse_attrs(rel.get("attributes"))
            related_tables.append({
                "table": rel["name"],
                "relationship": rel.get("relationship", "RELATED"),
                "join_type": ra.get("join_type"),
                "join_condition": ra.get("join_condition"),
            })

        business_rules = []
        for rule in row.get("rules", []):
            if not rule.get("name"):
                continue
            rua = self._parse_attrs(rule.get("attributes"))
            business_rules.append({
                "name": rule["name"],
                "description": rule.get("summary", "") or "",
                "rule_type": rua.get("rule_type", ""),
                "expression": rua.get("expression", ""),
            })

        codesets = []
        for cs in row.get("codesets", []):
            if not cs.get("name"):
                continue
            csa = self._parse_attrs(cs.get("attributes"))
            codesets.append({
                "name": cs["name"],
                "description": cs.get("summary", "") or "",
                "codes": csa.get("codes", {}),
                "column_name": csa.get("column_name", ""),
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
        """Deduplicated list of table names from ranked results."""
        seen: dict[str, None] = {}
        for t in tables:
            if t.name not in seen:
                seen[t.name] = None
        for c in columns:
            tbl = c.attributes.get("table_name", "")
            if tbl and tbl not in seen:
                seen[tbl] = None
        return list(seen)
