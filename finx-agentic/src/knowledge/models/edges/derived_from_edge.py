from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class DerivedFromEdge(BaseEdge):
    """Column ──DERIVED_FROM──▶ Column  (data lineage)"""

    source_column: str
    source_table: str
    target_column: str
    target_table: str
    database: str
    transformation: str = ""

    def _edge_type(self) -> str:
        return EdgeType.DERIVED_FROM

    def _fact(self) -> str:
        return f"{self.source_table}.{self.source_column} is derived from {self.target_table}.{self.target_column}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "source_column": self.source_column,
            "source_table": self.source_table,
            "target_column": self.target_column,
            "target_table": self.target_table,
            "database": self.database,
            "transformation": self.transformation,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "DerivedFromEdge":
        attrs = edge.attributes or {}
        return cls(
            source_column=attrs.get("source_column", ""),
            source_table=attrs.get("source_table", ""),
            target_column=attrs.get("target_column", ""),
            target_table=attrs.get("target_table", ""),
            database=attrs.get("database", ""),
            transformation=attrs.get("transformation", ""),
        )
