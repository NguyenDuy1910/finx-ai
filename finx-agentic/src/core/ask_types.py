from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AskStatus(str, Enum):
    UNDERSTANDING = "understanding"
    SEARCHING = "searching"
    PLANNING = "planning"
    GENERATING = "generating"
    CORRECTING = "correcting"
    FINISHED = "finished"
    FAILED = "failed"
    STOPPED = "stopped"


class AskErrorCode(str, Enum):
    NO_RELEVANT_DATA = "NO_RELEVANT_DATA"
    NO_RELEVANT_SQL = "NO_RELEVANT_SQL"
    INTENT_NOT_SQL = "INTENT_NOT_SQL"
    TIMEOUT = "TIMEOUT"
    OTHERS = "OTHERS"


class UserIntent(str, Enum):
    TEXT_TO_SQL = "text_to_sql"
    SCHEMA_QUERY = "schema_query"
    MISLEADING_QUERY = "misleading_query"
    GENERAL = "general"
    CLARIFICATION_NEEDED = "clarification_needed"


class IntentClassificationResult(BaseModel):
    intent: UserIntent
    confidence: float = 0.0
    reasoning: str = ""
    rewritten_query: Optional[str] = None
    clarification_question: Optional[str] = None


class AskRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    database: Optional[str] = None
    histories: List[Dict[str, str]] = Field(default_factory=list)
    ignore_sql_reasoning: bool = False
    enable_column_pruning: bool = False
    custom_instruction: Optional[str] = None


class SQLCandidate(BaseModel):
    sql: str
    database: str = ""
    reasoning: str = ""
    tables_used: List[str] = Field(default_factory=list)
    has_partition_filter: bool = False
    confidence: float = 0.0


class AskResultResponse(BaseModel):
    query_id: str
    status: AskStatus
    intent: Optional[UserIntent] = None
    response: Optional[str] = None
    sql_candidates: List[SQLCandidate] = Field(default_factory=list)
    error_code: Optional[AskErrorCode] = None
    error_message: Optional[str] = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class StreamEvent(BaseModel):
    event: str
    data: Dict[str, Any] = Field(default_factory=dict)


class SQLDiagnosisResult(BaseModel):
    error_type: str = ""
    root_cause: str = ""
    suggestion: str = ""


class SQLCorrectionResult(BaseModel):
    corrected_sql: str
    reasoning: str = ""
    is_valid: bool = False
