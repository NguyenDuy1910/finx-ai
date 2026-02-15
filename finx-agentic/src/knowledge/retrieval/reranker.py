"""Intelligent Reranker — Multi-signal scoring for search results.

Scoring formula:
  Final = 0.30×TextMatch + 0.25×GraphRelevance + 0.20×DataQuality
        + 0.15×UsageFrequency + 0.10×BusinessContext
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RerankerWeights:
    """Scoring weight vector — sums to 1.0."""

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


@dataclass
class ScoredItem:
    """A candidate search result with decomposed scores."""

    name: str
    label: str
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)

    text_match_score: float = 0.0
    graph_relevance_score: float = 0.0
    data_quality_score: float = 0.0
    usage_frequency_score: float = 0.0
    business_context_score: float = 0.0
    final_score: float = 0.0

    match_type: str = ""
    hop_distance: int = 0
    source_level: str = ""
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
            "source_level": self.source_level,
            "context": self.context,
        }


class SearchReranker:
    """Stateless reranker — call ``rerank()`` with a list of ScoredItems."""

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
        """Score, filter, deduplicate and sort *items*."""
        thr = threshold if threshold is not None else self.confidence_threshold
        k = top_k if top_k is not None else self.top_k

        for item in items:
            self._compute_final_score(item)

        # deduplicate by (name, label)
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
    def compute_text_match(match_type: str, vector_similarity: float = 0.0) -> float:
        base = {
            "exact": 1.0,
            "synonym": 0.9,
            "partial": 0.7,
            "vector": 0.0,
            "graph_expansion": 0.4,
        }.get(match_type, 0.3)
        if match_type == "vector":
            return max(0.0, min(1.0, vector_similarity))
        return base

    @staticmethod
    def compute_graph_relevance(hop_distance: int = 0, centrality: float = 0.0) -> float:
        if hop_distance == 0:
            base = 1.0
        elif hop_distance == 1:
            base = 0.8
        elif hop_distance == 2:
            base = 0.5
        else:
            base = max(0.2, 1.0 - 0.3 * hop_distance)
        return min(1.0, base + centrality * 0.3)

    @staticmethod
    def compute_data_quality(
        has_description: bool = False,
        has_sample_values: bool = False,
        has_business_rules: bool = False,
        has_partition_keys: bool = False,
        column_completeness: float = 0.0,
    ) -> float:
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
    def compute_usage_frequency(
        frequency: int = 0,
        success_rate: float = 0.0,
        is_recent: bool = False,
    ) -> float:
        if frequency == 0:
            return 0.0
        freq_score = min(1.0, math.log1p(frequency) / math.log1p(100))
        combined = freq_score * max(0.1, success_rate)
        if is_recent:
            combined = min(1.0, combined + 0.1)
        return combined

    @staticmethod
    def compute_business_context(
        same_domain: bool = False,
        has_owner: bool = False,
        is_certified: bool = False,
    ) -> float:
        score = 0.0
        if same_domain:
            score += 0.50
        if has_owner:
            score += 0.20
        if is_certified:
            score += 0.30
        return min(1.0, score)
