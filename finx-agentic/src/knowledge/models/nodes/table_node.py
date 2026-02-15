from typing import Any, Dict, List, Optional

from pydantic import Field
from graphiti_core.nodes import EntityNode

from src.knowledge.models import BaseNode
from src.knowledge.models.enums import NodeLabel


class TableNode(BaseNode):
    database: str
    partition_keys: List[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    storage_format: str = ""
    location: str = ""

    def _label(self) -> str:
        return NodeLabel.TABLE

    def _node_name(self) -> str:
        return f"{self.database}.{self.name}"

    def _build_attributes(self) -> Dict[str, Any]:
        return {
            "database": self.database,
            "table_name": self.name,
            "partition_keys": self.partition_keys,
            "row_count": self.row_count,
            "storage_format": self.storage_format,
            "location": self.location,
        }

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "TableNode":
        attrs = node.attributes or {}
        db_table = node.name.split(".", 1)
        database = attrs.get("database", db_table[0] if len(db_table) > 1 else "")
        table_name = attrs.get("table_name", db_table[-1])
        return cls(
            name=table_name,
            database=database,
            description=node.summary or "",
            partition_keys=attrs.get("partition_keys", []),
            row_count=attrs.get("row_count"),
            storage_format=attrs.get("storage_format", ""),
            location=attrs.get("location", ""),
        )
