from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class QueryIntent(str, Enum):
    DATA_QUERY = "data_query"
    SCHEMA_QUERY = "schema_query"
    AGGREGATION = "aggregation"
    COMPARISON = "comparison"
    TREND = "trend"
    FILTER = "filter"
    JOIN = "join"
    UNKNOWN = "unknown"


class ParsedQuery(BaseModel):
    original_text: str
    intent: QueryIntent
    entities: List[str] = Field(default_factory=list)
    filters: List[str] = Field(default_factory=list)
    time_range: Optional[str] = None
    aggregations: List[str] = Field(default_factory=list)
    sort_fields: List[str] = Field(default_factory=list)
    limit: Optional[int] = None
    confidence: float = 0.0


class SchemaMatch(BaseModel):
    table_name: str
    database: str
    relevance_score: float = 0.0
    matched_columns: List[str] = Field(default_factory=list)
    description: str = ""
    partition_keys: List[str] = Field(default_factory=list)


class SchemaContext(BaseModel):
    tables: List[SchemaMatch] = Field(default_factory=list)
    relationships: List[Dict[str, str]] = Field(default_factory=list)
    suggested_joins: List[str] = Field(default_factory=list)
    partition_filters: Dict[str, str] = Field(default_factory=dict)


class GeneratedSQL(BaseModel):
    sql: str
    database: str
    reasoning: str = ""
    tables_used: List[str] = Field(default_factory=list)
    estimated_cost: Optional[str] = None
    has_partition_filter: bool = False


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    corrected_sql: Optional[str] = None


class QueryEpisode(BaseModel):
    natural_language: str
    parsed_query: ParsedQuery
    schema_context: SchemaContext
    generated_sql: GeneratedSQL
    validation: ValidationResult
    execution_success: bool = False
    user_feedback: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Text2SQLResult(BaseModel):
    query: str
    parsed: ParsedQuery
    schema_context: SchemaContext
    sql: GeneratedSQL
    validation: ValidationResult
    execution_result: Optional[Dict[str, Any]] = None
    episode_id: Optional[str] = None

