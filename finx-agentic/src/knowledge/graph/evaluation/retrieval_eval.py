from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.knowledge.graph.store import GraphStore
from src.knowledge.retrieval.graph_retriever import GraphRetriever

logger = logging.getLogger(__name__)


@dataclass
class _RetrievalQuery:
    """A single test query with expected results."""
    query: str
    expected_nodes: set[str]
    expected_neighbors: set[str]
    expected_context_contains: list[str]


@dataclass
class RetrievalScore:
    """Aggregated retrieval quality metrics."""

    total_queries: int = 0
    hits: int = 0
    reciprocal_ranks: list[float] = field(default_factory=list)
    precision_at_k_values: list[float] = field(default_factory=list)
    recall_values: list[float] = field(default_factory=list)
    context_hit_rates: list[float] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total_queries if self.total_queries > 0 else 0.0

    @property
    def mrr(self) -> float:
        """Mean Reciprocal Rank."""
        return sum(self.reciprocal_ranks) / len(self.reciprocal_ranks) if self.reciprocal_ranks else 0.0

    @property
    def avg_precision_at_k(self) -> float:
        return sum(self.precision_at_k_values) / len(self.precision_at_k_values) if self.precision_at_k_values else 0.0

    @property
    def avg_recall(self) -> float:
        return sum(self.recall_values) / len(self.recall_values) if self.recall_values else 0.0

    @property
    def avg_context_hit_rate(self) -> float:
        return sum(self.context_hit_rates) / len(self.context_hit_rates) if self.context_hit_rates else 0.0

    def summary(self) -> str:
        lines = [
            f"{'='*50}",
            f"  RETRIEVAL EVALUATION",
            f"{'='*50}",
            f"  Queries:          {self.total_queries}",
            f"  Hit Rate:         {self.hit_rate:.2%}",
            f"  MRR:              {self.mrr:.4f}",
            f"  Avg Precision@K:  {self.avg_precision_at_k:.2%}",
            f"  Avg Recall:       {self.avg_recall:.2%}",
            f"  Avg Context Hit:  {self.avg_context_hit_rate:.2%}",
        ]
        if self.details:
            lines.append("")
            lines.append("  Per-query breakdown:")
            for d in self.details:
                status = "HIT" if d.get("hit") else "MISS"
                lines.append(
                    f"    [{status}] \"{d['query'][:40]}\" "
                    f"P={d.get('precision', 0):.0%} R={d.get('recall', 0):.0%} "
                    f"RR={d.get('rr', 0):.2f}"
                )
        lines.append(f"{'='*50}")
        return "\n".join(lines)


class RetrievalEvaluator:
    """Evaluate retrieval quality against curated test queries.

    Ground truth format (JSON)::

        [
            {
                "query": "bảng giao dịch tiền gửi",
                "expected_nodes": ["DM_DEPOSIT_TXN"],
                "expected_neighbors": ["DEPOSITS", "CORE_BANKING"],
                "expected_context_contains": ["tiền gửi"]
            }
        ]

    Args:
        store: ``GraphStore`` instance connected to FalkorDB.
        top_k: Number of results to retrieve per query.
    """

    def __init__(self, store: GraphStore, *, top_k: int = 10) -> None:
        self._retriever = GraphRetriever(store)
        self._top_k = top_k
        self._queries: list[_RetrievalQuery] = []

    def add_query(
        self,
        query: str,
        expected_nodes: list[str],
        expected_neighbors: list[str] | None = None,
        expected_context_contains: list[str] | None = None,
    ) -> None:
        """Register a test query."""
        self._queries.append(_RetrievalQuery(
            query=query,
            expected_nodes={n.upper().strip() for n in expected_nodes},
            expected_neighbors={n.upper().strip() for n in (expected_neighbors or [])},
            expected_context_contains=expected_context_contains or [],
        ))

    def load_queries_json(self, data: list[dict[str, Any]]) -> None:
        """Load test queries from a list of dicts (parsed JSON)."""
        for item in data:
            self.add_query(
                query=item["query"],
                expected_nodes=item.get("expected_nodes", []),
                expected_neighbors=item.get("expected_neighbors", []),
                expected_context_contains=item.get("expected_context_contains", []),
            )

    def evaluate(self) -> RetrievalScore:
        """Run all queries and compute metrics."""
        score = RetrievalScore(total_queries=len(self._queries))

        for tq in self._queries:
            self._evaluate_query(tq, score)

        return score

    def _evaluate_query(self, tq: _RetrievalQuery, score: RetrievalScore) -> None:
        try:
            subgraph = self._retriever.search_and_expand(
                tq.query, top_k=self._top_k,
            )
        except Exception as exc:
            logger.warning("Retrieval failed for '%s': %s", tq.query, exc)
            score.reciprocal_ranks.append(0.0)
            score.precision_at_k_values.append(0.0)
            score.recall_values.append(0.0)
            score.context_hit_rates.append(0.0)
            score.details.append({"query": tq.query, "hit": False, "error": str(exc)})
            return

        returned_nodes = [n.node_id for n in subgraph.seed_nodes]
        returned_set = set(returned_nodes)

        neighbor_names = {nb.get("tgt", "").upper().strip() for nb in subgraph.neighbors}

        all_expected = tq.expected_nodes | tq.expected_neighbors

        found_in_seeds = returned_set & tq.expected_nodes
        found_in_neighbors = neighbor_names & tq.expected_neighbors
        is_hit = bool(found_in_seeds or found_in_neighbors)
        if is_hit:
            score.hits += 1

        rr = 0.0
        for i, node_id in enumerate(returned_nodes, 1):
            if node_id in tq.expected_nodes:
                rr = 1.0 / i
                break
        score.reciprocal_ranks.append(rr)

        precision = len(found_in_seeds) / len(returned_nodes) if returned_nodes else 0.0
        score.precision_at_k_values.append(precision)

        if all_expected:
            found_total = (found_in_seeds | found_in_neighbors) & all_expected
            recall = len(found_total) / len(all_expected)
        else:
            recall = 1.0
        score.recall_values.append(recall)

        context = GraphRetriever.format_context(subgraph)
        if tq.expected_context_contains:
            context_lower = context.lower()
            hits = sum(1 for s in tq.expected_context_contains if s.lower() in context_lower)
            ctx_rate = hits / len(tq.expected_context_contains)
        else:
            ctx_rate = 1.0
        score.context_hit_rates.append(ctx_rate)

        score.details.append({
            "query": tq.query,
            "hit": is_hit,
            "returned_seeds": returned_nodes[:5],
            "found_seeds": sorted(found_in_seeds),
            "found_neighbors": sorted(found_in_neighbors),
            "precision": precision,
            "recall": recall,
            "rr": rr,
            "context_hit_rate": ctx_rate,
        })
