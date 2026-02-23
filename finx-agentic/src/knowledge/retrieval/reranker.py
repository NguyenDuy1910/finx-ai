"""Hierarchical reranker with intent-aware weight profiles and score propagation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RerankerWeights:
    """Scoring weight vector, auto-normalized to sum to 1.0."""

    text_match: float = 0.30
    graph_relevance: float = 0.25
    data_quality: float = 0.20
    usage_frequency: float = 0.15
    business_context: float = 0.10

    def __post_init__(self) -> None:
        total = (
            self.text_match + self.graph_relevance + self.data_quality
            + self.usage_frequency + self.business_context
        )
        if abs(total - 1.0) > 0.01:
            self.text_match /= total
            self.graph_relevance /= total
            self.data_quality /= total
            self.usage_frequency /= total
            self.business_context /= total


# weight profiles keyed by intent from QueryUnderstanding
INTENT_WEIGHT_PROFILES: Dict[str, RerankerWeights] = {
    "text_to_sql": RerankerWeights(
        text_match=0.25, graph_relevance=0.30,
        data_quality=0.20, usage_frequency=0.15, business_context=0.10,
    ),
    "relationship_discovery": RerankerWeights(
        text_match=0.15, graph_relevance=0.45,
        data_quality=0.10, usage_frequency=0.10, business_context=0.20,
    ),
    "aggregation_query": RerankerWeights(
        text_match=0.20, graph_relevance=0.20,
        data_quality=0.30, usage_frequency=0.20, business_context=0.10,
    ),
    "knowledge_lookup": RerankerWeights(
        text_match=0.35, graph_relevance=0.15,
        data_quality=0.15, usage_frequency=0.10, business_context=0.25,
    ),
    "schema_query": RerankerWeights(
        text_match=0.30, graph_relevance=0.25,
        data_quality=0.25, usage_frequency=0.05, business_context=0.15,
    ),
}


def weights_for_intent(
    intent: Optional[str],
    weight_overrides: Optional[Dict[str, float]] = None,
) -> RerankerWeights:
    """Return the weight profile for a given intent, with optional LLM overrides.

    Parameters
    ----------
    intent:
        The classified intent key (e.g. "text_to_sql").
    weight_overrides:
        Optional dict of dimension -> float overrides from the LLM intent analyzer.
        Keys that are ``None`` or missing fall back to the profile default.
    """
    if intent and intent in INTENT_WEIGHT_PROFILES:
        base = INTENT_WEIGHT_PROFILES[intent]
    else:
        base = RerankerWeights()

    if not weight_overrides:
        return base

    # Merge: override values take precedence, None/missing → keep base
    return RerankerWeights(
        text_match=weight_overrides.get("text_match") if weight_overrides.get("text_match") is not None else base.text_match,
        graph_relevance=weight_overrides.get("graph_relevance") if weight_overrides.get("graph_relevance") is not None else base.graph_relevance,
        data_quality=weight_overrides.get("data_quality") if weight_overrides.get("data_quality") is not None else base.data_quality,
        usage_frequency=weight_overrides.get("usage_frequency") if weight_overrides.get("usage_frequency") is not None else base.usage_frequency,
        business_context=weight_overrides.get("business_context") if weight_overrides.get("business_context") is not None else base.business_context,
    )


@dataclass
class ScoredItem:
    """A candidate search result with decomposed scores per dimension."""

    name: str
    label: str
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)

    # per-dimension scores in [0, 1]
    text_match_score: float = 0.0
    graph_relevance_score: float = 0.0
    data_quality_score: float = 0.0
    usage_frequency_score: float = 0.0
    business_context_score: float = 0.0

    # computed by reranker
    final_score: float = 0.0

    match_type: str = ""       # exact | synonym | vector | graph_expansion | pattern
    hop_distance: int = 0
    source_layer: str = ""     # layer1_domain .. layer5_pattern
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "summary": self.summary,
            "attributes": self.attributes,
            "final_score": round(self.final_score, 4),
            "scores": {
                "text_match": round(self.text_match_score, 4),
                "graph_relevance": round(self.graph_relevance_score, 4),
                "data_quality": round(self.data_quality_score, 4),
                "usage_frequency": round(self.usage_frequency_score, 4),
                "business_context": round(self.business_context_score, 4),
            },
            "match_type": self.match_type,
            "hop_distance": self.hop_distance,
            "source_layer": self.source_layer,
            "context": self.context,
        }


class SearchReranker:
    """Reranker with hierarchical score propagation and intent-aware weights."""

    def __init__(
        self,
        weights: Optional[RerankerWeights] = None,
        confidence_threshold: float = 0.35,
        top_k: int = 10,
    ):
        self.weights = weights or RerankerWeights()
        self.confidence_threshold = confidence_threshold
        self.top_k = top_k

    def rerank(
        self,
        items: List[ScoredItem],
        *,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> List[ScoredItem]:
        """Score, deduplicate, filter and sort items."""
        thr = threshold if threshold is not None else self.confidence_threshold
        k = top_k if top_k is not None else self.top_k

        for item in items:
            self._compute_final_score(item)

        # deduplicate by (label, name), keep highest score
        seen: dict[str, ScoredItem] = {}
        for item in items:
            key = f"{item.label}:{item.name}"
            if key not in seen or item.final_score > seen[key].final_score:
                seen[key] = item

        filtered = [it for it in seen.values() if it.final_score >= thr]
        filtered.sort(key=lambda it: it.final_score, reverse=True)
        return filtered[:k]

    def _compute_final_score(self, item: ScoredItem) -> None:
        w = self.weights
        item.final_score = (
            w.text_match * item.text_match_score
            + w.graph_relevance * item.graph_relevance_score
            + w.data_quality * item.data_quality_score
            + w.usage_frequency * item.usage_frequency_score
            + w.business_context * item.business_context_score
        )

    @staticmethod
    def propagate_scores(
        items: List[ScoredItem],
        domain_scores: Dict[str, float],
        table_scores: Dict[str, float],
    ) -> None:
        """Cascade parent scores down the hierarchy: domain -> table -> column."""
        domain_boost_factor = 0.30
        table_boost_factor = 0.20
        for item in items:
            item_domain = item.attributes.get("domain", "")
            if item.label == "Table" and item_domain in domain_scores:
                boost = domain_boost_factor * domain_scores[item_domain]
                item.business_context_score = min(1.0, item.business_context_score + boost)
            if item.label == "Column":
                parent_table = item.attributes.get("table_name", "")
                if parent_table in table_scores:
                    boost = table_boost_factor * table_scores[parent_table]
                    item.graph_relevance_score = min(1.0, item.graph_relevance_score + boost)
                col_domain = item.attributes.get("domain", "")
                if col_domain in domain_scores:
                    boost = domain_boost_factor * 0.5 * domain_scores[col_domain]
                    item.business_context_score = min(1.0, item.business_context_score + boost)

    @staticmethod
    def score_text_match(match_type: str, similarity: float = 0.0) -> float:
        """Return text_match score based on how the item was found."""
        base_scores = {
            "exact": 1.0,
            "synonym": 0.9,
            "partial": 0.7,
            "graph_expansion": 0.4,
            "pattern": 0.6,
        }
        if match_type == "vector":
            return max(0.0, min(1.0, similarity))
        return base_scores.get(match_type, 0.3)

    @staticmethod
    def score_graph_relevance(hop_distance: int = 0) -> float:
        """Return graph_relevance score based on hop distance from query anchor."""
        if hop_distance == 0:
            return 1.0
        if hop_distance == 1:
            return 0.8
        if hop_distance == 2:
            return 0.5
        return max(0.2, 1.0 - 0.3 * hop_distance)

    @staticmethod
    def score_data_quality(
        has_description: bool = False,
        has_sample_values: bool = False,
        has_business_rules: bool = False,
        has_partition_keys: bool = False,
        column_completeness: float = 0.0,
    ) -> float:
        """Return data_quality score from metadata completeness signals."""
        score = 0.0
        if has_description:
            score += 0.20
        if has_sample_values:
            score += 0.20
        if has_business_rules:
            score += 0.25
        if has_partition_keys:
            score += 0.15
        score += 0.20 * min(1.0, column_completeness)
        return min(1.0, score)

    @staticmethod
    def score_usage_frequency(
        frequency: int = 0,
        success_rate: float = 0.0,
        is_recent: bool = False,
    ) -> float:
        """Return usage_frequency score from historical query stats."""
        if frequency == 0:
            return 0.0
        freq_score = min(1.0, math.log1p(frequency) / math.log1p(100))
        combined = freq_score * max(0.1, success_rate)
        if is_recent:
            combined = min(1.0, combined + 0.1)
        return combined

    @staticmethod
    def score_business_context(
        same_domain: bool = False,
        has_owner: bool = False,
        is_certified: bool = False,
    ) -> float:
        """Return business_context score from domain and ownership signals."""
        score = 0.0
        if same_domain:
            score += 0.50
        if has_owner:
            score += 0.20
        if is_certified:
            score += 0.30
        return min(1.0, score)
