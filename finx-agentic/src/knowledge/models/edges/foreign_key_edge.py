from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class ForeignKeyEdge(BaseEdge):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    database: str
    constraint_name: str = ""

    def _edge_type(self) -> str:
        return EdgeType.FOREIGN_KEY

    def _fact(self) -> str:
        return f"{self.source_table}.{self.source_column} references {self.target_table}.{self.target_column}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "source_table": self.source_table,
            "source_column": self.source_column,
            "target_table": self.target_table,
            "target_column": self.target_column,
            "database": self.database,
            "constraint_name": self.constraint_name,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "ForeignKeyEdge":
        attrs = edge.attributes or {}
        return cls(
            source_table=attrs.get("source_table", ""),
            source_column=attrs.get("source_column", ""),
            target_table=attrs.get("target_table", ""),
            target_column=attrs.get("target_column", ""),
            database=attrs.get("database", ""),
            constraint_name=attrs.get("constraint_name", ""),
        )
