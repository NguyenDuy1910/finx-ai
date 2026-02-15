from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = ""


class PaginationParams(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


class HealthResponse(BaseModel):
    status: str
    graph_connected: bool
    version: str = "0.1.0"


class TableCreate(BaseModel):
    name: str
    database: str
    description: str = ""
    partition_keys: List[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    storage_format: str = ""
    location: str = ""


class TableUpdate(BaseModel):
    description: Optional[str] = None
    partition_keys: Optional[List[str]] = None
    row_count: Optional[int] = None
    storage_format: Optional[str] = None
    location: Optional[str] = None


class TableResponse(BaseModel):
    uuid: str
    name: str
    database: str
    description: str = ""
    partition_keys: List[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    storage_format: str = ""
    location: str = ""


class ColumnCreate(BaseModel):
    name: str
    table_name: str
    database: str
    data_type: str = "string"
    description: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_partition: bool = False
    is_nullable: bool = True
    sample_values: List[str] = Field(default_factory=list)


class ColumnUpdate(BaseModel):
    data_type: Optional[str] = None
    description: Optional[str] = None
    is_primary_key: Optional[bool] = None
    is_foreign_key: Optional[bool] = None
    is_partition: Optional[bool] = None
    is_nullable: Optional[bool] = None
    sample_values: Optional[List[str]] = None


class ColumnResponse(BaseModel):
    uuid: str
    name: str
    table_name: str
    database: str
    data_type: str = "string"
    description: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_partition: bool = False
    is_nullable: bool = True
    sample_values: List[str] = Field(default_factory=list)


class BusinessEntityCreate(BaseModel):
    name: str
    domain: str = "business"
    description: str = ""
    synonyms: List[str] = Field(default_factory=list)
    mapped_tables: List[str] = Field(default_factory=list)


class BusinessEntityUpdate(BaseModel):
    domain: Optional[str] = None
    description: Optional[str] = None
    synonyms: Optional[List[str]] = None
    mapped_tables: Optional[List[str]] = None


class BusinessEntityResponse(BaseModel):
    uuid: str
    name: str
    domain: str = "business"
    description: str = ""
    synonyms: List[str] = Field(default_factory=list)
    mapped_tables: List[str] = Field(default_factory=list)


class QueryPatternCreate(BaseModel):
    name: str
    intent: str
    pattern: str
    sql_template: str = ""
    tables_involved: List[str] = Field(default_factory=list)
    frequency: int = 0


class QueryPatternResponse(BaseModel):
    uuid: str
    name: str
    intent: str
    pattern: str
    sql_template: str = ""
    frequency: int = 0
    tables_involved: List[str] = Field(default_factory=list)


class JoinCreate(BaseModel):
    source_table: str
    target_table: str
    database: str
    join_type: str = "INNER"
    source_column: str = ""
    target_column: str = ""
    join_condition: str = ""


class ForeignKeyCreate(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    database: str
    constraint_name: str = ""


class EntityMappingCreate(BaseModel):
    entity_name: str
    table_name: str
    database: str
    confidence: float = 1.0
    mapping_type: str = "direct"


class EdgeResponse(BaseModel):
    relationship: str
    target: str
    target_labels: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    database: Optional[str] = None
    top_k: int = Field(5, ge=1, le=50)
    threshold: float = Field(0.5, ge=0.0, le=1.0)


class SearchResultItem(BaseModel):
    name: str
    label: str
    summary: str
    score: float
    attributes: Dict[str, Any] = Field(default_factory=dict)


class TableContextResponse(BaseModel):
    table: str
    database: str
    description: str
    partition_keys: List[str] = Field(default_factory=list)
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    related_tables: List[Dict[str, Any]] = Field(default_factory=list)


class SchemaSearchResponse(BaseModel):
    tables: List[SearchResultItem] = Field(default_factory=list)
    columns: List[SearchResultItem] = Field(default_factory=list)
    entities: List[SearchResultItem] = Field(default_factory=list)
    patterns: List[Dict[str, Any]] = Field(default_factory=list)
    context: List[TableContextResponse] = Field(default_factory=list)
    ranked_results: List[Dict[str, Any]] = Field(default_factory=list)
    query_analysis: Optional[Dict[str, Any]] = None
    search_metadata: Dict[str, Any] = Field(default_factory=dict)


class RecordQueryRequest(BaseModel):
    natural_language: str
    generated_sql: str
    tables_used: List[str] = Field(default_factory=list)
    database: str = ""
    intent: str = ""
    success: bool = True
    execution_time_ms: Optional[int] = None
    row_count: Optional[int] = None
    error_message: str = ""


class RecordFeedbackRequest(BaseModel):
    natural_language: str
    generated_sql: str
    feedback: str
    rating: Optional[int] = Field(None, ge=1, le=5)
    corrected_sql: str = ""


class RecordPatternRequest(BaseModel):
    intent: str
    pattern: str
    sql_template: str
    tables_involved: List[str] = Field(default_factory=list)
    example_queries: List[str] = Field(default_factory=list)


class RecordSchemaRequest(BaseModel):
    table_name: str
    database: str
    columns: List[Dict[str, Any]]
    partition_keys: List[str] = Field(default_factory=list)
    description: str = ""
    action: str = "created"


class EpisodeResponse(BaseModel):
    episode_id: str


class ContextRequest(BaseModel):
    query: str
    database: Optional[str] = None
    top_k: int = Field(5, ge=1, le=50)


class ContextResponse(BaseModel):
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    patterns: List[Dict[str, Any]] = Field(default_factory=list)
    context: List[Dict[str, Any]] = Field(default_factory=list)
    similar_queries: List[Dict[str, Any]] = Field(default_factory=list)
    feedback: List[Dict[str, Any]] = Field(default_factory=list)


class Text2SQLRequest(BaseModel):
    query: str
    database: Optional[str] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class Text2SQLResponse(BaseModel):
    query: str
    sql: str
    database: str = ""
    tables_used: List[str] = Field(default_factory=list)
    reasoning: str = ""
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    episode_id: Optional[str] = None


class StatsResponse(BaseModel):
    entities: Dict[str, int] = Field(default_factory=dict)
    episodes: Dict[str, int] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str
    database: Optional[str] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    available_databases: List[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    intent: str
    response: str = ""
    sql: Optional[str] = None
    database: Optional[str] = None
    tables_used: List[str] = Field(default_factory=list)
    context_used: Dict[str, Any] = Field(default_factory=dict)
    episode_id: Optional[str] = None
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    suggestions: List[str] = Field(default_factory=list)

