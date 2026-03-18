from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Semantic entities
# ---------------------------------------------------------------------------


class MetricEntity(BaseModel):
    """A quantifiable business measure such as revenue, transaction count, or churn rate.
    Metrics are the primary targets of analytical questions and link to KPI formulas,
    dimensions, and authoritative tables that back their computation."""

    description: str = ""
    unit: str = ""
    aggregation_method: str = ""
    business_owner: str = ""
    tags: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class BusinessTermEntity(BaseModel):
    """A domain-specific term, abbreviation, or jargon used in finance conversations.
    Maps user language to canonical metrics or dimension values via ALIAS_OF / REFERS_TO edges."""

    term: str
    definition: str = ""
    scope: str = "global"
    domain: str = ""
    synonyms: list[str] = Field(default_factory=list)


class DimensionEntity(BaseModel):
    """An analytical axis used to slice or group metrics, such as region, product line,
    or time period. Dimensions define the GROUP BY and WHERE semantics in generated SQL."""

    description: str = ""
    data_type: str = ""
    cardinality: str = ""
    hierarchy_level: str = ""


class DimensionValueEntity(BaseModel):
    """A concrete allowed value within a dimension, e.g. 'VN' for the country dimension.
    Linked to its parent Dimension via VALID_VALUE_FOR and reachable from BusinessTerm
    through ALIAS_OF when users refer to it by a colloquial name."""

    value: str
    label: str = ""
    dimension_name: str = ""
    is_active: bool = True


class KPIFormulaEntity(BaseModel):
    """A calculation recipe that defines how a metric is computed from other metrics
    or raw columns. Linked to its parent Metric via CALCULATED_BY."""

    expression: str = ""
    input_metrics: list[str] = Field(default_factory=list)
    output_unit: str = ""
    notes: str = ""


class BusinessDefinitionEntity(BaseModel):
    """An approved, authoritative prose definition of a metric or business concept.
    Serves as the single source of truth for what a metric means and how it should
    be interpreted. Linked from Metric via DEFINED_AS."""

    body: str = ""
    effective_date: str = ""
    source_document: str = ""
    approved_by: str = ""


class TimeSemanticEntity(BaseModel):
    """A temporal concept that governs how date/time filters and aggregations work,
    such as fiscal year boundaries, calendar weeks, or reporting cut-off rules."""

    granularity: str = ""
    calendar_type: str = "gregorian"
    fiscal_offset_months: int = 0
    description: str = ""


# ---------------------------------------------------------------------------
# Physical data entities
# ---------------------------------------------------------------------------


class DatasetEntity(BaseModel):
    """A logical grouping of related tables within a database or data lake, e.g. a schema
    or catalog. Tables link to their parent Dataset via BELONGS_TO."""

    database: str = ""
    description: str = ""
    owner: str = ""
    tags: list[str] = Field(default_factory=list)


class TableEntity(BaseModel):
    """A physical or logical table in the data warehouse. The central node in the physical
    layer; columns are stored as embedded attributes (not separate entities).
    Metrics link here via BACKED_BY or AUTHORITATIVE_SOURCE_FOR to indicate which
    table is the canonical source.
    
    Each entry in `columns` is a pipe-delimited string:
      column_name|data_type|PK|partition|nullable|description
    Example: "transaction_id|VARCHAR|PK|||Unique transaction identifier"
    """

    table_name: str
    database: str = ""
    dataset: str = ""
    description: str = ""
    ai_description: str = ""
    domain: str = ""
    tags: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    partition_keys: list[str] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    storage_format: str = ""
    certification_status: str = ""
    deprecation_status: str = ""
    columns: list[str] = Field(default_factory=list)


class ViewEntity(BaseModel):
    """A database view built on top of one or more base tables. Captures the SQL definition
    and the list of source tables it depends on."""

    view_name: str
    database: str = ""
    definition_sql: str = ""
    description: str = ""
    source_tables: list[str] = Field(default_factory=list)


class AggregationGrainEntity(BaseModel):
    """The granularity at which a table is pre-aggregated, e.g. daily per customer.
    Tables link here via HAS_GRAIN so the query engine knows the finest level of
    detail available without further aggregation."""

    grain_columns: list[str] = Field(default_factory=list)
    time_granularity: str = ""
    description: str = ""


class JoinPathEntity(BaseModel):
    """A reusable join recipe between two tables, capturing join type, condition, and
    cardinality. Linked to both tables via CONNECTS edges so the SQL generator can
    assemble multi-table queries safely."""

    left_table: str = ""
    right_table: str = ""
    join_type: str = "INNER"
    join_condition: str = ""
    cardinality: str = ""


class SemanticModelEntity(BaseModel):
    """A curated collection of metrics, dimensions, and tables that form a coherent
    analytical subject area. Acts as the bridge between business semantics and
    physical data layout."""

    description: str = ""
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Query entities
# ---------------------------------------------------------------------------


class QueryIntentEntity(BaseModel):
    """A classified user intent derived from a natural-language question, e.g.
    'compare monthly revenue by region'. Links to the metrics it REQUESTS,
    the dimensions it GROUPS_BY or FILTERS_BY, and the SQLPattern it USES."""

    description: str = ""
    intent_type: str = ""
    complexity: str = "simple"
    required_metrics: list[str] = Field(default_factory=list)
    required_dimensions: list[str] = Field(default_factory=list)


class SQLPatternEntity(BaseModel):
    """A reusable, certified SQL template that safely answers a class of query intents.
    Contains a parameterised SQL skeleton, the tables it touches, and links to the
    ConstraintRules and ValidationRules that must be satisfied before execution."""

    template_sql: str = ""
    description: str = ""
    pattern_type: str = ""
    tables_used: list[str] = Field(default_factory=list)
    is_certified: bool = False


class ConstraintRuleEntity(BaseModel):
    """A hard guard-rail that a SQL pattern must satisfy, such as mandatory WHERE clauses,
    row-limit caps, or required partition filters. Violation blocks query execution."""

    rule_expression: str = ""
    severity: str = "error"
    description: str = ""


class ValidationRuleEntity(BaseModel):
    """A post-execution check applied to query results, such as row-count sanity,
    NULL-ratio thresholds, or value-range assertions. Linked from SQLPattern
    via VALIDATED_BY."""

    check_type: str = ""
    expected_condition: str = ""
    description: str = ""


class ResultShapeEntity(BaseModel):
    """The expected output schema of a query: column names, approximate row count, and
    a visualization hint. QueryIntent links here via RETURNS_SHAPE so downstream
    consumers know what to expect."""

    columns: list[str] = Field(default_factory=list)
    row_estimate: str = ""
    visualization_hint: str = ""


class ExampleQuestionEntity(BaseModel):
    """A natural-language question paired with its expected SQL answer. Used for few-shot
    retrieval during query generation and for regression testing of the text2sql agent."""

    question: str
    intent: str = ""
    expected_sql: str = ""
    difficulty: str = "medium"
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Governance entities
# ---------------------------------------------------------------------------


class UserRoleEntity(BaseModel):
    """A named role in the access-control model, e.g. analyst, manager, auditor.
    Links to metrics and tables via CAN_ACCESS to define what data each role
    is permitted to query."""

    role_name: str
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class AccessPolicyEntity(BaseModel):
    """A governance rule that restricts access to a metric or table based on user roles.
    Metrics and tables link here via RESTRICTED_BY; changes are tracked through
    PolicyChange nodes."""

    policy_name: str
    description: str = ""
    allowed_roles: list[str] = Field(default_factory=list)
    denied_roles: list[str] = Field(default_factory=list)
    scope: str = ""


class DataSensitivityEntity(BaseModel):
    """A classification level for data sensitivity, e.g. public, internal, confidential,
    or PII. Determines masking and access requirements for columns or tables."""

    level: str
    description: str = ""
    handling_requirements: str = ""


class SourceAuthorityEntity(BaseModel):
    """Designates who or which team is the authoritative owner of a table's data.
    Tables link here via HAS_AUTHORITY to resolve conflicting definitions or
    data-quality disputes."""

    authority_level: str = ""
    description: str = ""
    owner_team: str = ""


class FreshnessPolicyEntity(BaseModel):
    """Defines how fresh the data in a table or metric must be, including maximum
    acceptable staleness and refresh schedule. Metrics link here via REFRESHED_UNDER."""

    max_staleness: str = ""
    refresh_schedule: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Learning / evolution entities
# ---------------------------------------------------------------------------


class DefinitionChangeEntity(BaseModel):
    """A versioned record of a change to a metric's business definition. Links to
    the affected Metric via UPDATED, enabling the agent to detect stale knowledge."""

    change_id: str
    previous_value: str = ""
    new_value: str = ""
    changed_by: str = ""
    changed_at: str = ""
    reason: str = ""


class SchemaChangeEntity(BaseModel):
    """A record of a DDL change to a table such as column additions, renames, or type
    changes. Links to the affected Table via MODIFIED_SCHEMA_OF."""

    change_id: str
    change_type: str = ""
    affected_columns: list[str] = Field(default_factory=list)
    changed_at: str = ""
    description: str = ""


class PolicyChangeEntity(BaseModel):
    """A record of a change to an access or governance policy. Links to the affected
    AccessPolicy via UPDATED for audit trail and staleness detection."""

    change_id: str
    previous_policy: str = ""
    new_policy: str = ""
    changed_by: str = ""
    changed_at: str = ""
    reason: str = ""


class AnalystFeedbackEntity(BaseModel):
    """Human feedback from an analyst on a generated SQL pattern, indicating correctness,
    style improvements, or domain corrections. Links to SQLPattern via CORRECTED_BY."""

    feedback_id: str
    analyst: str = ""
    comment: str = ""
    sentiment: str = ""
    created_at: str = ""


class UsageExampleEntity(BaseModel):
    """A real-world question-and-SQL pair that was successfully executed. Links to
    QueryIntent via EXEMPLIFIES to provide few-shot examples during retrieval."""

    question: str = ""
    sql: str = ""
    tables_used: list[str] = Field(default_factory=list)
    source: str = ""


class QueryFailureCaseEntity(BaseModel):
    """A recorded instance where a generated SQL query failed at execution or produced
    incorrect results. Links to the offending SQLPattern via INVALIDATES or WARNS_ABOUT
    to prevent the agent from repeating the same mistake."""

    case_id: str
    failing_sql: str = ""
    error_message: str = ""
    root_cause: str = ""
    resolution: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Metric": MetricEntity,
    "BusinessTerm": BusinessTermEntity,
    "Dimension": DimensionEntity,
    "DimensionValue": DimensionValueEntity,
    "KPIFormula": KPIFormulaEntity,
    "BusinessDefinition": BusinessDefinitionEntity,
    "TimeSemantic": TimeSemanticEntity,
    "Dataset": DatasetEntity,
    "Table": TableEntity,
    "View": ViewEntity,
    "AggregationGrain": AggregationGrainEntity,
    "JoinPath": JoinPathEntity,
    "SemanticModel": SemanticModelEntity,
    "QueryIntent": QueryIntentEntity,
    "SQLPattern": SQLPatternEntity,
    "ConstraintRule": ConstraintRuleEntity,
    "ValidationRule": ValidationRuleEntity,
    "ResultShape": ResultShapeEntity,
    "ExampleQuestion": ExampleQuestionEntity,
    "UserRole": UserRoleEntity,
    "AccessPolicy": AccessPolicyEntity,
    "DataSensitivity": DataSensitivityEntity,
    "SourceAuthority": SourceAuthorityEntity,
    "FreshnessPolicy": FreshnessPolicyEntity,
    "DefinitionChange": DefinitionChangeEntity,
    "SchemaChange": SchemaChangeEntity,
    "PolicyChange": PolicyChangeEntity,
    "AnalystFeedback": AnalystFeedbackEntity,
    "UsageExample": UsageExampleEntity,
    "QueryFailureCase": QueryFailureCaseEntity,
}
