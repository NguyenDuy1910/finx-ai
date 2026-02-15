from typing import Any, Dict

from graphiti_core.edges import EntityEdge

from src.knowledge.models import BaseEdge
from src.knowledge.models.edges.edge_types import EdgeType


class HasRuleEdge(BaseEdge):
    """BusinessEntity ──HAS_RULE──▶ BusinessRule"""

    entity_name: str
    rule_name: str

    def _edge_type(self) -> str:
        return EdgeType.HAS_RULE

    def _fact(self) -> str:
        return f"Entity '{self.entity_name}' has rule '{self.rule_name}'"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "entity_name": self.entity_name,
            "rule_name": self.rule_name,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "HasRuleEdge":
        attrs = edge.attributes or {}
        return cls(
            entity_name=attrs.get("entity_name", ""),
            rule_name=attrs.get("rule_name", ""),
        )


class AppliesToEdge(BaseEdge):
    """BusinessRule ──APPLIES_TO──▶ Table | Column"""

    rule_name: str
    target_name: str
    target_type: str = "table"  # "table" | "column"

    def _edge_type(self) -> str:
        return EdgeType.APPLIES_TO

    def _fact(self) -> str:
        return f"Rule '{self.rule_name}' applies to {self.target_type} '{self.target_name}'"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "target_name": self.target_name,
            "target_type": self.target_type,
        }

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "AppliesToEdge":
        attrs = edge.attributes or {}
        return cls(
            rule_name=attrs.get("rule_name", ""),
            target_name=attrs.get("target_name", ""),
            target_type=attrs.get("target_type", "table"),
        )
