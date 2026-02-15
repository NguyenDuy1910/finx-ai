from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class QueryPatternEdge(BaseEdge):
    pattern_name: str
    table_name: str
    database: str
    role: str = "source"
    frequency: int = 0

    def _edge_type(self) -> str:
        return EdgeType.QUERY_USES_TABLE

    def _fact(self) -> str:
        return f"Query pattern '{self.pattern_name}' uses table {self.database}.{self.table_name} as {self.role}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "pattern_name": self.pattern_name,
            "table_name": self.table_name,
            "database": self.database,
            "role": self.role,
            "frequency": self.frequency,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "QueryPatternEdge":
        attrs = edge.attributes or {}
        return cls(
            pattern_name=attrs.get("pattern_name", ""),
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            role=attrs.get("role", "source"),
            frequency=attrs.get("frequency", 0),
        )
