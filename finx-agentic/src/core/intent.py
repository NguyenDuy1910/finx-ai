from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserIntent(str, Enum):
    DATA_QUERY = "data_query"
    SCHEMA_EXPLORATION = "schema_exploration"
    RELATIONSHIP_DISCOVERY = "relationship_discovery"
    KNOWLEDGE_LOOKUP = "knowledge_lookup"
    FEEDBACK = "feedback"
    CLARIFICATION = "clarification"
    GENERAL = "general"


class IntentClassification(BaseModel):
    intent: UserIntent = UserIntent.GENERAL
    confidence: float = 0.0
    entities: List[str] = Field(default_factory=list)
    database: Optional[str] = None
    requires_graph_context: bool = False
    reasoning: str = ""
    ambiguous: bool = False
    missing_info: List[str] = Field(default_factory=list)
    alternative_intents: List[str] = Field(default_factory=list)


class RouterContext(BaseModel):
    intent: IntentClassification
    graph_context: Dict[str, Any] = Field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class RouterResult(BaseModel):
    intent: UserIntent
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
