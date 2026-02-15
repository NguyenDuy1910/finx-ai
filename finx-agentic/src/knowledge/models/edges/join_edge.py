from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class JoinEdge(BaseEdge):
    source_table: str
    target_table: str
    database: str
    join_type: str = "INNER"
    source_column: str = ""
    target_column: str = ""
    join_condition: str = ""
    discovered_from: str = "manual"
    usage_count: int = 0

    def _edge_type(self) -> str:
        return EdgeType.JOIN

    def _fact(self) -> str:
        condition = self.join_condition or f"{self.source_table}.{self.source_column} = {self.target_table}.{self.target_column}"
        return f"{self.source_table} joins {self.target_table} on {condition}"

    def _build_attributes(self) -> Dict[str, Any]:
        condition = self.join_condition or f"{self.source_table}.{self.source_column} = {self.target_table}.{self.target_column}"
        return {
            "source_table": self.source_table,
            "target_table": self.target_table,
            "database": self.database,
            "join_type": self.join_type,
            "source_column": self.source_column,
            "target_column": self.target_column,
            "join_condition": condition,
            "discovered_from": self.discovered_from,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "JoinEdge":
        attrs = edge.attributes or {}
        return cls(
            source_table=attrs.get("source_table", ""),
            target_table=attrs.get("target_table", ""),
            database=attrs.get("database", ""),
            join_type=attrs.get("join_type", "INNER"),
            source_column=attrs.get("source_column", ""),
            target_column=attrs.get("target_column", ""),
            join_condition=attrs.get("join_condition", ""),
            discovered_from=attrs.get("discovered_from", "manual"),
            usage_count=attrs.get("usage_count", 0),
        )
