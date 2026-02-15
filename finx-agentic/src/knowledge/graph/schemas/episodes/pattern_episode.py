import json
from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field
from graphiti_core.nodes import EpisodicNode, EpisodeType


class PatternEpisode(BaseModel):
    """Records a learned query pattern."""

    intent: str
    pattern: str
    sql_template: str
    tables_involved: List[str] = Field(default_factory=list)
    example_queries: List[str] = Field(default_factory=list)
    frequency: int = 1

    def to_episodic_node(self, group_id: str) -> EpisodicNode:
        content = json.dumps({
            "category": "pattern_learned",
            "intent": self.intent,
            "pattern": self.pattern,
            "sql_template": self.sql_template,
            "tables_involved": self.tables_involved,
            "example_queries": self.example_queries,
            "frequency": self.frequency,
        })
        return EpisodicNode(
            name=f"pattern_{self.intent}",
            group_id=group_id,
            source=EpisodeType.json,
            source_description=f"Learned pattern: {self.intent} - {self.pattern[:80]}",
            content=content,
            valid_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_episodic_node(cls, node: EpisodicNode) -> "PatternEpisode":
        data = json.loads(node.content) if node.content else {}
        return cls(
            intent=data.get("intent", ""),
            pattern=data.get("pattern", ""),
            sql_template=data.get("sql_template", ""),
            tables_involved=data.get("tables_involved", []),
            example_queries=data.get("example_queries", []),
            frequency=data.get("frequency", 1),
        )
