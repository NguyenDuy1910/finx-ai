from typing import Any, Dict, List

from pydantic import Field
from graphiti_core.nodes import EntityNode

from src.knowledge.models import BaseNode
from src.knowledge.models.enums import NodeLabel


class BusinessEntityNode(BaseNode):
    domain: str = "business"
    synonyms: List[str] = Field(default_factory=list)
    mapped_tables: List[str] = Field(default_factory=list)

    def _label(self) -> str:
        return NodeLabel.BUSINESS_ENTITY

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "synonyms": self.synonyms,
            "mapped_tables": self.mapped_tables,
        }

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "BusinessEntityNode":
        attrs = node.attributes or {}
        return cls(
            name=node.name,
            domain=attrs.get("domain", "business"),
            description=node.summary or "",
            synonyms=attrs.get("synonyms", []),
            mapped_tables=attrs.get("mapped_tables", []),
        )
