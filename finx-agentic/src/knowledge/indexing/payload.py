from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

EpisodeSourceType = Literal["json", "text", "message"]


class CanonicalPayload(BaseModel):
    model_config = {"extra": "forbid"}


class MetricDefinitionPayload(CanonicalPayload):
    metric_id: str
    metric_name: str
    aliases: list[str] = Field(default_factory=list)
    definition: str
    unit: str | None = None
    aggregation: str | None = None
    default_time_grain: str | None = None
    valid_dimensions: list[str] = Field(default_factory=list)
    authoritative_source_ids: list[str] = Field(default_factory=list)
    owner_team: str | None = None
    evidence_text: str | None = None


class TermAliasPayload(CanonicalPayload):
    term_id: str
    surface_form: str
    refers_to_type: str
    refers_to_id: str
    locale: str | None = None
    notes: str | None = None
    evidence_text: str | None = None


class TableMappingPayload(CanonicalPayload):
    table_id: str
    table_name: str
    dataset_id: str | None = None
    warehouse: str | None = None
    metric_ids: list[str] = Field(default_factory=list)
    column_ids: list[str] = Field(default_factory=list)
    grain: str | None = None
    join_paths: list[str] = Field(default_factory=list)
    is_authoritative: bool = False
    freshness_policy_id: str | None = None
    evidence_text: str | None = None


class ColumnMappingPayload(CanonicalPayload):
    column_id: str
    column_name: str
    table_id: str
    semantic_type: str | None = None
    metric_id: str | None = None
    dimension_id: str | None = None
    data_type: str | None = None


class QueryPatternPayload(CanonicalPayload):
    pattern_id: str
    pattern_name: str
    intent_id: str
    metric_ids: list[str] = Field(default_factory=list)
    required_dimensions: list[str] = Field(default_factory=list)
    required_filters: list[str] = Field(default_factory=list)
    forbidden_joins: list[str] = Field(default_factory=list)
    validation_rules: list[str] = Field(default_factory=list)
    template_sql: str
    result_shape: str
    evidence_text: str | None = None


class AccessPolicyPayload(CanonicalPayload):
    policy_id: str
    policy_name: str
    allowed_roles: list[str] = Field(default_factory=list)
    allowed_metric_ids: list[str] = Field(default_factory=list)
    allowed_table_ids: list[str] = Field(default_factory=list)
    restricted_table_ids: list[str] = Field(default_factory=list)
    restricted_column_ids: list[str] = Field(default_factory=list)
    sensitivity: str | None = None
    evidence_text: str | None = None


class AnalystFeedbackPayload(CanonicalPayload):
    feedback_id: str
    question_text: str
    incorrect_object_id: str | None = None
    incorrect_object_type: str | None = None
    corrected_object_id: str | None = None
    corrected_object_type: str | None = None
    reason: str | None = None
    impact: str | None = None
    action: str | None = None
    evidence_text: str | None = None


PayloadUnion = (
    MetricDefinitionPayload
    | TermAliasPayload
    | TableMappingPayload
    | QueryPatternPayload
    | AccessPolicyPayload
    | AnalystFeedbackPayload
)


class CanonicalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    event_version: str = "v1"
    group_id: str
    reference_time: datetime
    source_system: str
    source_record_id: str
    source_type: EpisodeSourceType = "json"
    source_description: str
    authority_score: int = 50
    confidence_score: float = 1.0
    tags: list[str] = Field(default_factory=list)
    payload: PayloadUnion


class CanonicalEventBatch(BaseModel):
    events: list[CanonicalEvent] = Field(default_factory=list)