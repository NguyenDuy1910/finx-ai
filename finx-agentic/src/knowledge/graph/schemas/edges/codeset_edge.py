from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.graph.schemas import BaseEdge
from src.knowledge.graph.schemas.edges.edge_types import EdgeType


class HasCodeSetEdge(BaseEdge):
    """Column ──HAS_CODESET──▶ CodeSet"""

    column_name: str
    table_name: str
    database: str
    codeset_name: str

    def _edge_type(self) -> str:
        return EdgeType.HAS_CODESET

    def _fact(self) -> str:
        return f"Column {self.database}.{self.table_name}.{self.column_name} uses code-set '{self.codeset_name}'"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "column_name": self.column_name,
            "table_name": self.table_name,
            "database": self.database,
            "codeset_name": self.codeset_name,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "HasCodeSetEdge":
        attrs = edge.attributes or {}
        return cls(
            column_name=attrs.get("column_name", ""),
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            codeset_name=attrs.get("codeset_name", ""),
        )
