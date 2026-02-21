from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.graph.schemas import BaseEdge
from src.knowledge.graph.schemas.edges.edge_types import EdgeType


class BelongsToDomainEdge(BaseEdge):
    """Table ──BELONGS_TO_DOMAIN──▶ Domain"""

    table_name: str
    database: str
    domain_name: str

    def _edge_type(self) -> str:
        return EdgeType.BELONGS_TO_DOMAIN

    def _fact(self) -> str:
        return f"Table {self.database}.{self.table_name} belongs to domain '{self.domain_name}'"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "database": self.database,
            "domain_name": self.domain_name,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "BelongsToDomainEdge":
        attrs = edge.attributes or {}
        return cls(
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            domain_name=attrs.get("domain_name", ""),
        )


class ContainsEntityEdge(BaseEdge):
    """Domain ──CONTAINS_ENTITY──▶ BusinessEntity"""

    domain_name: str
    entity_name: str

    def _edge_type(self) -> str:
        return EdgeType.CONTAINS_ENTITY

    def _fact(self) -> str:
        return f"Domain '{self.domain_name}' contains entity '{self.entity_name}'"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "domain_name": self.domain_name,
            "entity_name": self.entity_name,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "ContainsEntityEdge":
        attrs = edge.attributes or {}
        return cls(
            domain_name=attrs.get("domain_name", ""),
            entity_name=attrs.get("entity_name", ""),
        )
