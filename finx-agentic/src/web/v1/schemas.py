from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    database: Optional[str] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class AskResponse(BaseModel):
    intent: str
    response: str = ""
    sql: Optional[str] = None
    database: Optional[str] = None
    tables_used: List[str] = Field(default_factory=list)
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    suggestions: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    database: Optional[str] = None
    domain: Optional[str] = None
    entities: Optional[List[str]] = None
    top_k: int = 5


class SearchResponse(BaseModel):
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    patterns: List[Dict[str, Any]] = Field(default_factory=list)
    context: List[Dict[str, Any]] = Field(default_factory=list)


class TableDetailResponse(BaseModel):
    table: Optional[Dict[str, Any]] = None
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class RelatedTablesResponse(BaseModel):
    table: str
    relations: List[Dict[str, Any]] = Field(default_factory=list)


class JoinPathResponse(BaseModel):
    source: str
    target: str
    direct_joins: List[Dict[str, Any]] = Field(default_factory=list)
    shared_intermediates: List[str] = Field(default_factory=list)


class IndexSchemaRequest(BaseModel):
    schema_path: str
    database: Optional[str] = None
    skip_existing: bool = False


class IndexSchemaResponse(BaseModel):
    tables: int = 0
    columns: int = 0
    entities: int = 0
    edges: int = 0
    domains: int = 0
    skipped: int = 0


class SyncRequest(BaseModel):
    database: str
    tables: Optional[List[str]] = None
    schema_path: Optional[str] = None


class SyncResponse(BaseModel):
    status: str
    details: Dict[str, Any] = Field(default_factory=dict)


class GraphStatsResponse(BaseModel):
    entities: Dict[str, Any] = Field(default_factory=dict)
    episodes: Dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    natural_language: str
    generated_sql: str
    feedback: str
    rating: Optional[int] = None
    corrected_sql: str = ""


class FeedbackResponse(BaseModel):
    episode_id: str
    status: str = "stored"


class Text2SQLRequest(BaseModel):
    query: str
    database: Optional[str] = None
    session_id: Optional[str] = None


class Text2SQLResponse(BaseModel):
    query: str
    sql: Optional[str] = None
    database: Optional[str] = None
    reasoning: str = ""
    tables_used: List[str] = Field(default_factory=list)
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ExecuteSQLRequest(BaseModel):
    sql: str
    database: Optional[str] = None
    timeout: int = 60


class ExecuteSQLResponse(BaseModel):
    success: bool
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: Optional[int] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
