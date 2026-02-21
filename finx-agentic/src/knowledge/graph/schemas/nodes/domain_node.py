from typing import Any, Dict, List

from pydantic import Field
from graphiti_core.nodes import EntityNode

from src.knowledge.graph.schemas import BaseNode
from src.knowledge.graph.schemas.enums import NodeLabel


class DomainNode(BaseNode):
    """A business domain grouping (e.g. 'payments', 'lending', 'customer_management')."""

    owner: str = ""
    tags: List[str] = Field(default_factory=list)

    def _label(self) -> str:
        return NodeLabel.DOMAIN

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "owner": self.owner,
            "tags": self.tags,
        }

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "DomainNode":
        attrs = node.attributes or {}
        return cls(
            name=node.name,
            description=node.summary or "",
            owner=attrs.get("owner", ""),
            tags=attrs.get("tags", []),
        )
