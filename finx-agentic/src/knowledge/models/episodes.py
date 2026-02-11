import json
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from graphiti_core.nodes import EpisodicNode, EpisodeType


class EpisodeCategory(str, Enum):
    SCHEMA_DEFINITION = "schema_definition"
    QUERY_EXECUTION = "query_execution"
    USER_FEEDBACK = "user_feedback"
    PATTERN_LEARNED = "pattern_learned"
    SCHEMA_CHANGE = "schema_change"


class SchemaEpisode(BaseModel):
    table_name: str
    database: str
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    partition_keys: List[str] = Field(default_factory=list)
    description: str = ""
    action: str = "created"

    def to_episodic_node(self, group_id: str) -> EpisodicNode:
        content = json.dumps({
            "category": EpisodeCategory.SCHEMA_DEFINITION,
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


class QueryEpisode(BaseModel):
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
            "category": EpisodeCategory.QUERY_EXECUTION,
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


class FeedbackEpisode(BaseModel):
    natural_language: str
    generated_sql: str
    feedback: str
    rating: Optional[int] = None
    corrected_sql: str = ""
    success: bool = True

    def to_episodic_node(self, group_id: str) -> EpisodicNode:
        content = json.dumps({
            "category": EpisodeCategory.USER_FEEDBACK,
            "natural_language": self.natural_language,
            "generated_sql": self.generated_sql,
            "feedback": self.feedback,
            "rating": self.rating,
            "corrected_sql": self.corrected_sql,
            "success": self.success,
        })
        return EpisodicNode(
            name=f"feedback_{self.natural_language[:50]}",
            group_id=group_id,
            source=EpisodeType.json,
            source_description=f"User feedback: {self.feedback[:100]}",
            content=content,
            valid_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_episodic_node(cls, node: EpisodicNode) -> "FeedbackEpisode":
        data = json.loads(node.content) if node.content else {}
        return cls(
            natural_language=data.get("natural_language", ""),
            generated_sql=data.get("generated_sql", ""),
            feedback=data.get("feedback", ""),
            rating=data.get("rating"),
            corrected_sql=data.get("corrected_sql", ""),
            success=data.get("success", True),
        )


class PatternEpisode(BaseModel):
    intent: str
    pattern: str
    sql_template: str
    tables_involved: List[str] = Field(default_factory=list)
    example_queries: List[str] = Field(default_factory=list)
    frequency: int = 1

    def to_episodic_node(self, group_id: str) -> EpisodicNode:
        content = json.dumps({
            "category": EpisodeCategory.PATTERN_LEARNED,
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

