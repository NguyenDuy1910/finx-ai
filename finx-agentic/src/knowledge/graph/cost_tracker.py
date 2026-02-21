"""Embedding cost tracker for graph operations."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingCall:
    node_label: str
    node_name: str
    text_length: int
    estimated_tokens: int
    cost_usd: float
    duration_s: float


@dataclass
class GraphCostTracker:
    embedding_model: str = "text-embedding-3-large"
    calls: List[EmbeddingCall] = field(default_factory=list)

    def add(self, call: EmbeddingCall) -> None:
        self.calls.append(call)

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def total_tokens(self) -> int:
        return sum(c.estimated_tokens for c in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_duration_s(self) -> float:
        return sum(c.duration_s for c in self.calls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "embedding_model": self.embedding_model,
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_duration_s": round(self.total_duration_s, 3),
        }

    def print_summary(self) -> None:
        header = (
            f"{'Label':<20} {'Node Name':<30} {'Tokens':>8} "
            f"{'Duration':>9} {'Cost ($)':>10}"
        )
        sep = "-" * 80
        lines = [
            "",
            "=" * 80,
            "GRAPH DB EMBEDDING COST SUMMARY",
            "=" * 80,
            header,
            sep,
        ]
        for c in self.calls:
            lines.append(
                f"{c.node_label:<20} {c.node_name[:29]:<30} {c.estimated_tokens:>8,} "
                f"{c.duration_s:>8.3f}s ${c.cost_usd:>9.6f}"
            )
        lines.append(sep)
        lines.append(
            f"{'TOTAL':<20} {f'{self.total_calls} calls':<30} {self.total_tokens:>8,} "
            f"{self.total_duration_s:>8.3f}s ${self.total_cost_usd:>9.6f}"
        )
        lines.append("=" * 80)
        logger.info("\n".join(lines))
