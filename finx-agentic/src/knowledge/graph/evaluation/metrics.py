from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from src.knowledge.graph.client import FalkorDBClient
from src.knowledge.graph.models import GRAPH_FIELD_SEP, NodeData
from src.knowledge.graph.store import GraphStore

logger = logging.getLogger(__name__)


@dataclass
class GraphQualityReport:
    total_nodes: int = 0
    total_edges: int = 0

    nodes_by_label: dict[str, int] = field(default_factory=dict)
    edges_by_type: dict[str, int] = field(default_factory=dict)
    nodes_by_domain: dict[str, int] = field(default_factory=dict)

    nodes_missing_description: int = 0
    nodes_missing_source_ids: int = 0
    nodes_missing_domain: int = 0

    orphan_nodes: int = 0
    self_loop_edges: int = 0
    duplicate_edges: int = 0

    avg_degree: float = 0.0
    max_degree: int = 0
    graph_density: float = 0.0
    isolated_labels: list[str] = field(default_factory=list)

    orphan_node_samples: list[dict[str, str]] = field(default_factory=list)
    missing_desc_samples: list[dict[str, str]] = field(default_factory=list)

    @property
    def completeness_score(self) -> float:
        if self.total_nodes == 0:
            return 0.0
        desc_ratio = 1 - (self.nodes_missing_description / self.total_nodes)
        src_ratio = 1 - (self.nodes_missing_source_ids / self.total_nodes)
        domain_ratio = 1 - (self.nodes_missing_domain / self.total_nodes)
        return round(desc_ratio * 0.5 + src_ratio * 0.3 + domain_ratio * 0.2, 4)

    @property
    def structural_score(self) -> float:
        if self.total_nodes == 0:
            return 0.0
        orphan_penalty = self.orphan_nodes / self.total_nodes
        loop_penalty = (self.self_loop_edges / max(self.total_edges, 1)) * 0.5
        return round(max(0.0, 1.0 - orphan_penalty - loop_penalty), 4)

    @property
    def label_coverage_score(self) -> float:
        known_labels = {
            "Table", "Dataset", "Column", "BusinessTerm",
            "Metric", "Dimension", "SourceAuthority", "UserRole", "Concept",
        }
        found = known_labels & set(self.nodes_by_label.keys())
        return round(len(found) / len(known_labels), 4)

    @property
    def edge_type_coverage_score(self) -> float:
        known_types = {
            "BELONGS_TO", "HAS_COLUMN", "BACKED_BY", "REFERS_TO", "ALIAS_OF",
            "RELATED_TO", "DEFINED_AS", "OWNED_BY", "JOINS_WITH", "PART_OF",
        }
        found = known_types & set(self.edges_by_type.keys())
        return round(len(found) / len(known_types), 4)

    @property
    def domain_balance_score(self) -> float:
        if not self.nodes_by_domain:
            return 0.0
        counts = list(self.nodes_by_domain.values())
        total = sum(counts)
        if total == 0:
            return 0.0
        n = len(counts)
        probs = [c / total for c in counts]
        entropy = -sum(p * math.log(p) for p in probs if p > 0)
        max_entropy = math.log(n) if n > 1 else 1.0
        return round(entropy / max_entropy if max_entropy > 0 else 0.0, 4)

    @property
    def overall_score(self) -> float:
        return round(
            self.completeness_score * 0.35
            + self.structural_score * 0.35
            + self.label_coverage_score * 0.15
            + self.domain_balance_score * 0.15,
            4,
        )

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "  KNOWLEDGE GRAPH QUALITY REPORT",
            "=" * 60,
            f"  Nodes: {self.total_nodes}  |  Edges: {self.total_edges}",
            f"  Avg degree: {self.avg_degree:.2f}  |  Max degree: {self.max_degree}",
            f"  Graph density: {self.graph_density:.6f}",
            "",
            "  Label distribution:",
        ]
        for label, count in sorted(self.nodes_by_label.items(), key=lambda x: -x[1]):
            lines.append(f"    {label:20s} {count:>6d}")
        lines.append("")
        lines.append("  Edge type distribution:")
        for etype, count in sorted(self.edges_by_type.items(), key=lambda x: -x[1]):
            lines.append(f"    {etype:20s} {count:>6d}")
        lines.append("")
        lines.append("  Domain distribution:")
        for domain, count in sorted(self.nodes_by_domain.items(), key=lambda x: -x[1]):
            lines.append(f"    {domain:20s} {count:>6d}")
        lines.append("")
        lines.append("  Completeness:")
        lines.append(f"    Missing description : {self.nodes_missing_description}")
        lines.append(f"    Missing source_ids  : {self.nodes_missing_source_ids}")
        lines.append(f"    Missing domain      : {self.nodes_missing_domain}")
        lines.append("")
        lines.append("  Structural issues:")
        lines.append(f"    Orphan nodes        : {self.orphan_nodes}")
        lines.append(f"    Self-loop edges     : {self.self_loop_edges}")
        lines.append(f"    Duplicate edges     : {self.duplicate_edges}")
        if self.isolated_labels:
            lines.append(f"    Isolated labels     : {', '.join(self.isolated_labels)}")
        lines.append("")
        lines.append("  Scores (0.0 - 1.0):")
        lines.append(f"    Completeness        : {self.completeness_score:.4f}")
        lines.append(f"    Structural          : {self.structural_score:.4f}")
        lines.append(f"    Label coverage      : {self.label_coverage_score:.4f}")
        lines.append(f"    Edge type coverage  : {self.edge_type_coverage_score:.4f}")
        lines.append(f"    Domain balance      : {self.domain_balance_score:.4f}")
        lines.append(f"    Overall             : {self.overall_score:.4f}")
        lines.append("=" * 60)
        return "\n".join(lines)


class GraphMetrics:
    SAMPLE_LIMIT = 20

    def __init__(self, client: FalkorDBClient) -> None:
        self._client = client
        self._store = GraphStore(client)

    def evaluate(self) -> GraphQualityReport:
        report = GraphQualityReport()
        self._count_totals(report)
        self._label_distribution(report)
        self._edge_type_distribution(report)
        self._domain_distribution(report)
        self._completeness_checks(report)
        self._structural_checks(report)
        self._connectivity(report)
        return report

    def _count_totals(self, r: GraphQualityReport) -> None:
        stats = self._store.stats()
        r.total_nodes = stats.get("nodes", 0)
        r.total_edges = stats.get("edges", 0)

    def _label_distribution(self, r: GraphQualityReport) -> None:
        result = self._client.execute(
            "MATCH (n:Entity) RETURN n.label AS lbl, count(n) AS c ORDER BY c DESC"
        )
        r.nodes_by_label = {
            row[0]: row[1]
            for row in (result.result_set or [])
            if row[0]
        }

    def _edge_type_distribution(self, r: GraphQualityReport) -> None:
        result = self._client.execute(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC"
        )
        r.edges_by_type = {
            row[0]: row[1]
            for row in (result.result_set or [])
            if row[0]
        }

    def _domain_distribution(self, r: GraphQualityReport) -> None:
        result = self._client.execute(
            "MATCH (n:Entity) WHERE n.domain IS NOT NULL AND n.domain <> '' "
            "RETURN n.domain AS d, count(n) AS c ORDER BY c DESC"
        )
        r.nodes_by_domain = {
            row[0]: row[1]
            for row in (result.result_set or [])
            if row[0]
        }

    def _completeness_checks(self, r: GraphQualityReport) -> None:
        result = self._client.execute(
            "MATCH (n:Entity) WHERE n.description IS NULL OR n.description = '' "
            "RETURN count(n) AS c"
        )
        r.nodes_missing_description = result.result_set[0][0] if result.result_set else 0

        result = self._client.execute(
            "MATCH (n:Entity) WHERE n.description IS NULL OR n.description = '' "
            "RETURN n.name AS name, n.label AS label LIMIT $limit",
            {"limit": self.SAMPLE_LIMIT},
        )
        r.missing_desc_samples = [
            {"name": row[0], "label": row[1] or ""}
            for row in (result.result_set or [])
        ]

        result = self._client.execute(
            "MATCH (n:Entity) WHERE n.source_ids IS NULL OR n.source_ids = '' "
            "RETURN count(n) AS c"
        )
        r.nodes_missing_source_ids = result.result_set[0][0] if result.result_set else 0

        result = self._client.execute(
            "MATCH (n:Entity) WHERE n.domain IS NULL OR n.domain = '' "
            "RETURN count(n) AS c"
        )
        r.nodes_missing_domain = result.result_set[0][0] if result.result_set else 0

    def _structural_checks(self, r: GraphQualityReport) -> None:
        result = self._client.execute(
            "MATCH (n:Entity) WHERE NOT (n)--() RETURN count(n) AS c"
        )
        r.orphan_nodes = result.result_set[0][0] if result.result_set else 0

        result = self._client.execute(
            "MATCH (n:Entity) WHERE NOT (n)--() "
            "RETURN n.name AS name, n.label AS label LIMIT $limit",
            {"limit": self.SAMPLE_LIMIT},
        )
        r.orphan_node_samples = [
            {"name": row[0], "label": row[1] or ""}
            for row in (result.result_set or [])
        ]

        result = self._client.execute(
            "MATCH (a:Entity)-[r]->(a) RETURN count(r) AS c"
        )
        r.self_loop_edges = result.result_set[0][0] if result.result_set else 0

        result = self._client.execute(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WITH a.name AS src, type(r) AS t, b.name AS tgt, count(r) AS c "
            "WHERE c > 1 "
            "RETURN sum(c - 1) AS dups"
        )
        r.duplicate_edges = result.result_set[0][0] if result.result_set else 0

    def _connectivity(self, r: GraphQualityReport) -> None:
        if r.total_nodes > 0:
            r.avg_degree = round((r.total_edges * 2) / r.total_nodes, 2)

            n = r.total_nodes
            max_possible_edges = n * (n - 1)
            if max_possible_edges > 0:
                r.graph_density = round(r.total_edges / max_possible_edges, 8)

        result = self._client.execute(
            "MATCH (n:Entity)-[r]-() "
            "WITH n, count(r) AS deg "
            "RETURN max(deg) AS max_deg"
        )
        r.max_degree = result.result_set[0][0] if result.result_set else 0

        labels_with_edges: set[str] = set()
        result = self._client.execute(
            "MATCH (n:Entity)-[r]-() RETURN DISTINCT n.label AS lbl"
        )
        for row in (result.result_set or []):
            if row[0]:
                labels_with_edges.add(row[0])

        r.isolated_labels = [
            lbl for lbl in r.nodes_by_label
            if lbl not in labels_with_edges
        ]
