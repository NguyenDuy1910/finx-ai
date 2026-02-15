from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import Field
from graphiti_core.nodes import EntityNode

from src.knowledge.models import BaseNode
from src.knowledge.models.enums import NodeLabel


class QueryPatternNode(BaseNode):
    intent: str
    pattern: str
    sql_template: str = ""
    frequency: int = 0
    success_rate: float = 0.0
    last_used: Optional[datetime] = None
    tables_involved: List[str] = Field(default_factory=list)

    def _label(self) -> str:
        return NodeLabel.QUERY_PATTERN

    def _node_name(self) -> str:
        return f"pattern_{self.intent}_{self.name}"

    def _summary(self) -> str:
        return f"{self.intent}: {self.pattern}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "pattern": self.pattern,
            "sql_template": self.sql_template,
            "frequency": self.frequency,
            "success_rate": self.success_rate,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "tables_involved": self.tables_involved,
        }

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "QueryPatternNode":
        attrs = node.attributes or {}
        last_used_str = attrs.get("last_used")
        last_used = datetime.fromisoformat(last_used_str) if last_used_str else None
        return cls(
            name=node.name,
            intent=attrs.get("intent", ""),
            pattern=attrs.get("pattern", ""),
            sql_template=attrs.get("sql_template", ""),
            frequency=attrs.get("frequency", 0),
            success_rate=attrs.get("success_rate", 0.0),
            last_used=last_used,
            tables_involved=attrs.get("tables_involved", []),
        )
