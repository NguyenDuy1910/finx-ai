from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class EntityMappingEdge(BaseEdge):
    entity_name: str
    table_name: str
    database: str
    confidence: float = 1.0
    mapping_type: str = "direct"

    def _edge_type(self) -> str:
        return EdgeType.ENTITY_MAPPING

    def _fact(self) -> str:
        return f"Entity '{self.entity_name}' maps to table {self.database}.{self.table_name}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "entity_name": self.entity_name,
            "table_name": self.table_name,
            "database": self.database,
            "confidence": self.confidence,
            "mapping_type": self.mapping_type,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "EntityMappingEdge":
        attrs = edge.attributes or {}
        return cls(
            entity_name=attrs.get("entity_name", ""),
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            confidence=attrs.get("confidence", 1.0),
            mapping_type=attrs.get("mapping_type", "direct"),
        )
