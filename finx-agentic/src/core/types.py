"""Core domain types shared across the codebase."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Query analysis ────────────────────────────────────────────────────────────

class QueryIntent(str, Enum):
    DATA_QUERY = "data_query"
    SCHEMA_QUERY = "schema_query"
    AGGREGATION = "aggregation"
    COMPARISON = "comparison"
    TREND = "trend"
    FILTER = "filter"
    JOIN = "join"
    CLARIFICATION_NEEDED = "clarification_needed"
    UNKNOWN = "unknown"


class ParsedQuery(BaseModel):
    original_text: str = ""
    intent: QueryIntent = QueryIntent.UNKNOWN
    entities: List[str] = Field(default_factory=list)
    filters: List[str] = Field(default_factory=list)
    time_range: Optional[str] = None
    aggregations: List[str] = Field(default_factory=list)
    sort_fields: List[str] = Field(default_factory=list)
    limit: Optional[int] = None
    confidence: float = 0.0
    clarification_question: Optional[str] = None
    ambiguity_reason: Optional[str] = None


class SchemaMatch(BaseModel):
    table_name: str
    database: str
    relevance_score: float = 0.0
    matched_columns: List[str] = Field(default_factory=list)
    description: str = ""
    partition_keys: List[str] = Field(default_factory=list)


class SchemaRelationship(BaseModel):
    from_table: str = ""
    from_column: str = ""
    to_table: str = ""
    to_column: str = ""
    relationship_type: str = ""


class PartitionFilter(BaseModel):
    table_name: str = ""
    filter_expression: str = ""


class SchemaContext(BaseModel):
    tables: List[SchemaMatch] = Field(default_factory=list)
    relationships: List[SchemaRelationship] = Field(default_factory=list)
    suggested_joins: List[str] = Field(default_factory=list)
    partition_filters: List[PartitionFilter] = Field(default_factory=list)


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


# ── Schema enrichment types ───────────────────────────────────────────────────

class ColumnSchema(BaseModel):
    """Raw column metadata as read from the data catalog."""
    name: str
    data_type: str = ""
    description: str = ""
    is_partition: bool = False
    is_primary_key: bool = False
    sample_values: List[str] = Field(default_factory=list)


class TableSchema(BaseModel):
    """Raw table metadata as read from the data catalog."""
    name: str
    database: str = ""
    description: str = ""
    location: str = ""
    storage_format: str = ""
    partition_keys: List[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    columns: List[ColumnSchema] = Field(default_factory=list)


class EnrichedColumn(BaseModel):
    """Column metadata enriched by LLM analysis."""
    name: str
    data_type: str = ""
    description: str = ""
    is_partition: bool = False
    is_primary_key: bool = False
    sample_values: List[str] = Field(default_factory=list)
    ai_description: str = ""
    business_terms: List[str] = Field(default_factory=list)
    column_type: str = ""


class Relationship(BaseModel):
    """A directed relationship between two tables, inferred by LLM."""
    source_table: str = ""
    target_table: str = ""
    relationship_type: str = "join"
    source_column: str = ""
    target_column: str = ""
    description: str = ""


class EnrichedSchema(BaseModel):
    """Table metadata enriched by LLM — ready for graph indexing."""
    name: str
    database: str = ""
    description: str = ""
    location: str = ""
    storage_format: str = ""
    partition_keys: List[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    columns: List[ColumnSchema] = Field(default_factory=list)
    # LLM-derived fields
    entity_name: str = ""
    domain: str = ""
    synonyms: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    ai_description: str = ""
    enriched_columns: List[EnrichedColumn] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    kg_nodes: List[Dict[str, Any]] = Field(default_factory=list)
    kg_edges: List[Dict[str, Any]] = Field(default_factory=list)
