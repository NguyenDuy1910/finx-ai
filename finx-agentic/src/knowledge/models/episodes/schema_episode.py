import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from graphiti_core.nodes import EpisodicNode, EpisodeType


class SchemaEpisode(BaseModel):
    """Records a schema definition / change event."""

    table_name: str
    database: str
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    partition_keys: List[str] = Field(default_factory=list)
    description: str = ""
    action: str = "created"

    def to_episodic_node(self, group_id: str) -> EpisodicNode:
        content = json.dumps({
            "category": "schema_definition",
            "table_name": self.table_name,
            "database": self.database,
            "columns": self.columns,
            "partition_keys": self.partition_keys,
            "description": self.description,
            "action": self.action,
        })
        return EpisodicNode(
            name=f"schema_{self.database}_{self.table_name}_{self.action}",
            group_id=group_id,
            source=EpisodeType.json,
            source_description=f"Schema {self.action} for {self.database}.{self.table_name}",
            content=content,
            valid_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_episodic_node(cls, node: EpisodicNode) -> "SchemaEpisode":
        data = json.loads(node.content) if node.content else {}
        return cls(
            table_name=data.get("table_name", ""),
            database=data.get("database", ""),
            columns=data.get("columns", []),
            partition_keys=data.get("partition_keys", []),
            description=data.get("description", ""),
            action=data.get("action", "created"),
        )
