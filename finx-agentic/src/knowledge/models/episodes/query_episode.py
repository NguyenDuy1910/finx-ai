import json
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field
from graphiti_core.nodes import EpisodicNode, EpisodeType


class QueryEpisode(BaseModel):
    """Records a Text2SQL query execution event."""

    natural_language: str
    generated_sql: str
    tables_used: List[str] = Field(default_factory=list)
    database: str = ""
    intent: str = ""
    success: bool = True
    execution_time_ms: Optional[int] = None
    row_count: Optional[int] = None
    error_message: str = ""

    def to_episodic_node(self, group_id: str) -> EpisodicNode:
        content = json.dumps({
            "category": "query_execution",
            "natural_language": self.natural_language,
            "generated_sql": self.generated_sql,
            "tables_used": self.tables_used,
            "database": self.database,
            "intent": self.intent,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "row_count": self.row_count,
            "error_message": self.error_message,
        })
        return EpisodicNode(
            name=f"query_{self.intent}_{self.database}",
            group_id=group_id,
            source=EpisodeType.json,
            source_description=f"Text2SQL query: {self.natural_language[:100]}",
            content=content,
            valid_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_episodic_node(cls, node: EpisodicNode) -> "QueryEpisode":
        data = json.loads(node.content) if node.content else {}
        return cls(
            natural_language=data.get("natural_language", ""),
            generated_sql=data.get("generated_sql", ""),
            tables_used=data.get("tables_used", []),
            database=data.get("database", ""),
            intent=data.get("intent", ""),
            success=data.get("success", True),
            execution_time_ms=data.get("execution_time_ms"),
            row_count=data.get("row_count"),
            error_message=data.get("error_message", ""),
        )
