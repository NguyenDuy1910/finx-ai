from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class SynonymEdge(BaseEdge):
    term: str
    synonym: str
    confidence: float = 1.0

    def _edge_type(self) -> str:
        return EdgeType.SYNONYM

    def _fact(self) -> str:
        return f"'{self.term}' is a synonym for '{self.synonym}'"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "term": self.term,
            "synonym": self.synonym,
            "confidence": self.confidence,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "SynonymEdge":
        attrs = edge.attributes or {}
        return cls(
            term=attrs.get("term", ""),
            synonym=attrs.get("synonym", ""),
            confidence=attrs.get("confidence", 1.0),
        )
