from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class ColumnMappingEdge(BaseEdge):
    """Column ──COLUMN_MAPPING──▶ BusinessEntity"""

    column_name: str
    table_name: str
    database: str
    entity_name: str
    confidence: float = 1.0

    def _edge_type(self) -> str:
        return EdgeType.COLUMN_MAPPING

    def _fact(self) -> str:
        return f"Column {self.database}.{self.table_name}.{self.column_name} maps to entity '{self.entity_name}'"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "column_name": self.column_name,
            "table_name": self.table_name,
            "database": self.database,
            "entity_name": self.entity_name,
            "confidence": self.confidence,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "ColumnMappingEdge":
        attrs = edge.attributes or {}
        return cls(
            column_name=attrs.get("column_name", ""),
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            entity_name=attrs.get("entity_name", ""),
            confidence=attrs.get("confidence", 1.0),
        )
