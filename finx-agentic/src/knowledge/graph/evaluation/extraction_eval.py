from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.knowledge.graph.models import ExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class ExtractionScore:
    """Precision / recall / F1 for a single extraction run."""

    node_true_positives: int = 0
    node_false_positives: int = 0
    node_false_negatives: int = 0

    edge_true_positives: int = 0
    edge_false_positives: int = 0
    edge_false_negatives: int = 0

    missed_nodes: list[str] = field(default_factory=list)
    extra_nodes: list[str] = field(default_factory=list)
    missed_edges: list[tuple[str, str, str]] = field(default_factory=list)
    extra_edges: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def node_precision(self) -> float:
        denom = self.node_true_positives + self.node_false_positives
        return self.node_true_positives / denom if denom > 0 else 0.0

    @property
    def node_recall(self) -> float:
        denom = self.node_true_positives + self.node_false_negatives
        return self.node_true_positives / denom if denom > 0 else 0.0

    @property
    def node_f1(self) -> float:
        p, r = self.node_precision, self.node_recall
        return (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

    @property
    def edge_precision(self) -> float:
        denom = self.edge_true_positives + self.edge_false_positives
        return self.edge_true_positives / denom if denom > 0 else 0.0

    @property
    def edge_recall(self) -> float:
        denom = self.edge_true_positives + self.edge_false_negatives
        return self.edge_true_positives / denom if denom > 0 else 0.0

    @property
    def edge_f1(self) -> float:
        p, r = self.edge_precision, self.edge_recall
        return (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

    @property
    def overall_f1(self) -> float:
        """Average of node F1 and edge F1."""
        return (self.node_f1 + self.edge_f1) / 2

    def summary(self) -> str:
        lines = [
            f"{'='*50}",
            f"  EXTRACTION EVALUATION",
            f"{'='*50}",
            f"  Nodes:  P={self.node_precision:.2%}  R={self.node_recall:.2%}  F1={self.node_f1:.2%}",
            f"    TP={self.node_true_positives}  FP={self.node_false_positives}  FN={self.node_false_negatives}",
            f"  Edges:  P={self.edge_precision:.2%}  R={self.edge_recall:.2%}  F1={self.edge_f1:.2%}",
            f"    TP={self.edge_true_positives}  FP={self.edge_false_positives}  FN={self.edge_false_negatives}",
            f"  Overall F1: {self.overall_f1:.2%}",
        ]
        if self.missed_nodes:
            lines.append(f"  Missed nodes: {', '.join(self.missed_nodes[:10])}")
        if self.extra_nodes:
            lines.append(f"  Extra nodes:  {', '.join(self.extra_nodes[:10])}")
        if self.missed_edges:
            lines.append(f"  Missed edges: {len(self.missed_edges)}")
        if self.extra_edges:
            lines.append(f"  Extra edges:  {len(self.extra_edges)}")
        lines.append(f"{'='*50}")
        return "\n".join(lines)


@dataclass
class _GroundTruth:
    """Expected entities and edges for a chunk."""
    chunk_id: str
    expected_nodes: set[str]
    expected_edges: set[tuple[str, str, str]]


class ExtractionEvaluator:
    """Compare extractor output against human-curated ground truth.

    Ground truth format (JSON)::

        [
            {
                "chunk_id": "abc123",
                "expected_nodes": ["DM_DEPOSIT_TXN", "DEPOSITS", "CORE_BANKING"],
                "expected_edges": [
                    ["DM_DEPOSIT_TXN", "BELONGS_TO", "DEPOSITS"],
                    ["DM_DEPOSIT_TXN", "BACKED_BY", "CORE_BANKING"]
                ]
            }
        ]
    """

    def __init__(self) -> None:
        self._ground_truths: dict[str, _GroundTruth] = {}

    def add_ground_truth(
        self,
        chunk_id: str,
        expected_nodes: list[str],
        expected_edges: list[tuple[str, str, str] | list[str]] | None = None,
    ) -> None:
        """Register expected entities/edges for a chunk."""
        node_set = {n.upper().strip() for n in expected_nodes}
        edge_set: set[tuple[str, str, str]] = set()
        for e in (expected_edges or []):
            if len(e) >= 3:
                edge_set.add((str(e[0]).upper().strip(), str(e[1]).upper().strip(), str(e[2]).upper().strip()))
        self._ground_truths[chunk_id] = _GroundTruth(
            chunk_id=chunk_id,
            expected_nodes=node_set,
            expected_edges=edge_set,
        )

    def load_ground_truth_json(self, data: list[dict[str, Any]]) -> None:
        """Load ground truth from a list of dicts (parsed JSON)."""
        for item in data:
            self.add_ground_truth(
                chunk_id=item["chunk_id"],
                expected_nodes=item.get("expected_nodes", []),
                expected_edges=item.get("expected_edges", []),
            )

    def evaluate(self, results: list[ExtractionResult]) -> ExtractionScore:
        """Score extraction results against all registered ground truths."""
        score = ExtractionScore()

        for result in results:
            gt = self._ground_truths.get(result.chunk_id)
            if gt is None:
                logger.debug("No ground truth for chunk %s — skipping", result.chunk_id)
                continue
            self._score_chunk(result, gt, score)

        return score

    def evaluate_single(self, result: ExtractionResult) -> ExtractionScore:
        """Score a single chunk extraction."""
        return self.evaluate([result])

    def _score_chunk(
        self, result: ExtractionResult, gt: _GroundTruth, score: ExtractionScore,
    ) -> None:
        extracted_nodes = {nid.upper().strip() for nid in result.nodes.keys()}

        tp_nodes = extracted_nodes & gt.expected_nodes
        fp_nodes = extracted_nodes - gt.expected_nodes
        fn_nodes = gt.expected_nodes - extracted_nodes

        score.node_true_positives += len(tp_nodes)
        score.node_false_positives += len(fp_nodes)
        score.node_false_negatives += len(fn_nodes)
        score.missed_nodes.extend(sorted(fn_nodes))
        score.extra_nodes.extend(sorted(fp_nodes))

        extracted_edges: set[tuple[str, str, str]] = set()
        for (src, tgt), raw_edges in result.edges.items():
            for re in raw_edges:
                extracted_edges.add((
                    re.src.upper().strip(),
                    re.edge_type.upper().strip(),
                    re.tgt.upper().strip(),
                ))

        tp_edges = extracted_edges & gt.expected_edges
        fp_edges = extracted_edges - gt.expected_edges
        fn_edges = gt.expected_edges - extracted_edges

        score.edge_true_positives += len(tp_edges)
        score.edge_false_positives += len(fp_edges)
        score.edge_false_negatives += len(fn_edges)
        score.missed_edges.extend(sorted(fn_edges))
        score.extra_edges.extend(sorted(fp_edges))
