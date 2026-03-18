from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel

DEFAULT_ENTITY_TYPE_NAMES = (
    "Metric",
    "BusinessTerm",
    "Dimension",
    "DimensionValue",
    "KPIFormula",
    "BusinessDefinition",
    "TimeSemantic",
    "Dataset",
    "Table",
    "View",
    "AggregationGrain",
    "JoinPath",
    "SemanticModel",
    "QueryIntent",
    "SQLPattern",
    "ConstraintRule",
    "ValidationRule",
    "ResultShape",
    "ExampleQuestion",
    "UserRole",
    "AccessPolicy",
    "DataSensitivity",
    "SourceAuthority",
    "FreshnessPolicy",
    "DefinitionChange",
    "SchemaChange",
    "PolicyChange",
    "AnalystFeedback",
    "UsageExample",
    "QueryFailureCase",
)

DEFAULT_EDGE_TYPE_NAMES = (
    "ALIAS_OF",
    "REFERS_TO",
    "DEFINED_AS",
    "CALCULATED_BY",
    "SCOPED_BY",
    "CAN_FILTER_BY",
    "VALID_VALUE_FOR",
    "BACKED_BY",
    "AUTHORITATIVE_SOURCE_FOR",
    "BELONGS_TO",
    "HAS_GRAIN",
    "JOINS_TO",
    "CONNECTS",
    "REQUESTS",
    "GROUPS_BY",
    "FILTERS_BY",
    "USES_PATTERN",
    "REQUIRES",
    "VALIDATED_BY",
    "RETURNS_SHAPE",
    "CAN_ACCESS",
    "RESTRICTED_BY",
    "REFRESHED_UNDER",
    "HAS_AUTHORITY",
    "UPDATED",
    "MODIFIED_SCHEMA_OF",
    "EXEMPLIFIES",
    "CORRECTED_BY",
    "INVALIDATES",
    "WARNS_ABOUT",
)


def _format_type_names(
    *,
    supplied: Mapping[str, type[BaseModel]] | None,
    fallback: tuple[str, ...],
) -> str:
    if supplied:
        names = sorted(supplied.keys())
    else:
        names = sorted(fallback)
    return ", ".join(names)


def build_extraction_instructions(
    *,
    entity_types: Mapping[str, type[BaseModel]] | None = None,
    edge_types: Mapping[str, type[BaseModel]] | None = None,
) -> str:
    entity_list = _format_type_names(
        supplied=entity_types,
        fallback=DEFAULT_ENTITY_TYPE_NAMES,
    )
    edge_list = _format_type_names(
        supplied=edge_types,
        fallback=DEFAULT_EDGE_TYPE_NAMES,
    )

    return f"""\
You are extracting ontology entities and relationships for a financial data knowledge graph.

CRITICAL RULES — read before extracting anything:
1. NEVER create entities for individual columns, column names, or column descriptions.
   Columns are attributes embedded inside their parent Table — not separate nodes.
2. NEVER create entities for synonyms, tags, or plain string values from the text.
3. Only create entities when there is STRONG evidence for a specific entity type.
4. Prefer FEWER, higher-quality entities over many low-value ones.
5. If unsure, DO NOT extract — skip it.

Allowed entity types: {entity_list}
Allowed edge types: {edge_list}

What to extract from schema/table data:
- ONE Table entity per table (with column_names, primary_keys, partition_keys as attributes)
- ONE Dataset entity if database/dataset is mentioned
- Metric entities ONLY if explicit business measures are defined
- BusinessTerm ONLY if a distinct business term/abbreviation is defined
- AggregationGrain if grain/granularity information is present
- JoinPath if explicit join conditions between tables are described

What NOT to extract:
- Individual columns (id, transaction_id, amount, etc.) — these are Table attributes
- Synonyms as separate entities
- Tags or labels as entities
- Descriptions as BusinessDefinition unless explicitly marked as an approved definition
- Inferred or guessed relationships not stated in the text

Edge rules:
- Table -> Dataset: BELONGS_TO
- Table -> Table: JOINS_TO (only if explicit join is described)
- Table -> AggregationGrain: HAS_GRAIN
- Metric -> Table: BACKED_BY, AUTHORITATIVE_SOURCE_FOR
- BusinessTerm -> Metric: ALIAS_OF, REFERS_TO
"""


EXTRACTION_INSTRUCTIONS = build_extraction_instructions()
