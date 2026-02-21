from typing import Any, Dict, List

from pydantic import Field
from graphiti_core.nodes import EntityNode

from src.knowledge.graph.schemas import BaseNode
from src.knowledge.graph.schemas.enums import NodeLabel


class ColumnNode(BaseNode):
    table_name: str
    database: str
    data_type: str = "string"
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_partition: bool = False
    is_nullable: bool = True
    sample_values: List[str] = Field(default_factory=list)

    def _label(self) -> str:
        return NodeLabel.COLUMN

    def _node_name(self) -> str:
        return f"{self.database}.{self.table_name}.{self.name}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "database": self.database,
            "table_name": self.table_name,
            "column_name": self.name,
            "data_type": self.data_type,
            "is_primary_key": self.is_primary_key,
            "is_foreign_key": self.is_foreign_key,
            "is_partition": self.is_partition,
            "is_nullable": self.is_nullable,
            "sample_values": self.sample_values,
        }

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "ColumnNode":
        attrs = node.attributes or {}
        parts = node.name.split(".")
        return cls(
            name=attrs.get("column_name", parts[-1] if parts else ""),
            table_name=attrs.get("table_name", parts[-2] if len(parts) > 1 else ""),
            database=attrs.get("database", parts[0] if len(parts) > 2 else ""),
            data_type=attrs.get("data_type", "string"),
            description=node.summary or "",
            is_primary_key=attrs.get("is_primary_key", False),
            is_foreign_key=attrs.get("is_foreign_key", False),
            is_partition=attrs.get("is_partition", False),
            is_nullable=attrs.get("is_nullable", True),
            sample_values=attrs.get("sample_values", []),
        )
