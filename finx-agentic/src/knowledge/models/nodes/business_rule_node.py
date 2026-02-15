from typing import Any, Dict, List

from pydantic import Field
from graphiti_core.nodes import EntityNode

from src.knowledge.models import BaseNode
from src.knowledge.models.enums import NodeLabel


class BusinessRuleNode(BaseNode):
    """A business rule / calculation logic in the banking domain.

    Examples:
    - "Số dư khả dụng = current_balance - hold_amount"
    - "Khách hàng VIP: AUM > 1 tỷ VND"
    """

    rule_type: str = "calculation"  # calculation | validation | classification | filter
    expression: str = ""  # human-readable formula or SQL snippet
    domain: str = ""
    priority: int = 0  # higher = more important
    tables_involved: List[str] = Field(default_factory=list)
    columns_involved: List[str] = Field(default_factory=list)

    def _label(self) -> str:
        return NodeLabel.BUSINESS_RULE

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "rule_type": self.rule_type,
            "expression": self.expression,
            "domain": self.domain,
            "priority": self.priority,
            "tables_involved": self.tables_involved,
            "columns_involved": self.columns_involved,
        }

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "BusinessRuleNode":
        attrs = node.attributes or {}
        return cls(
            name=node.name,
            description=node.summary or "",
            rule_type=attrs.get("rule_type", "calculation"),
            expression=attrs.get("expression", ""),
            domain=attrs.get("domain", ""),
            priority=attrs.get("priority", 0),
            tables_involved=attrs.get("tables_involved", []),
            columns_involved=attrs.get("columns_involved", []),
        )
