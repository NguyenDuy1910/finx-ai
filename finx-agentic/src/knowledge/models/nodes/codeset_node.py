from typing import Any, Dict

from pydantic import Field
from graphiti_core.nodes import EntityNode

from src.knowledge.models import BaseNode
from src.knowledge.models.enums import NodeLabel


class CodeSetNode(BaseNode):
    """A lookup / enumeration for coded column values.

    Example – column ``tranx_type``:
      codes = {"TF": "Chuyển khoản", "WD": "Rút tiền", "DP": "Nạp tiền"}
    """

    codes: Dict[str, str] = Field(default_factory=dict)  # code -> label
    column_name: str = ""
    table_name: str = ""
    database: str = ""

    def _label(self) -> str:
        return NodeLabel.CODE_SET

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "codes": self.codes,
            "column_name": self.column_name,
            "table_name": self.table_name,
            "database": self.database,
        }

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "CodeSetNode":
        attrs = node.attributes or {}
        return cls(
            name=node.name,
            description=node.summary or "",
            codes=attrs.get("codes", {}),
            column_name=attrs.get("column_name", ""),
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
        )
