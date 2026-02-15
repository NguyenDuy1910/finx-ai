from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class HasColumnEdge(BaseEdge):
    table_name: str
    database: str
    column_name: str
    ordinal_position: int = 0

    def _edge_type(self) -> str:
        return EdgeType.HAS_COLUMN

    def _fact(self) -> str:
        return f"Table {self.database}.{self.table_name} has column {self.column_name}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "database": self.database,
            "column_name": self.column_name,
            "ordinal_position": self.ordinal_position,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "HasColumnEdge":
        attrs = edge.attributes or {}
        return cls(
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            column_name=attrs.get("column_name", ""),
            ordinal_position=attrs.get("ordinal_position", 0),
        )
