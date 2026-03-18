from __future__ import annotations

from pydantic import BaseModel, Field


class AliasOf(BaseModel):
    """BusinessTerm is an alternative name for a Metric or DimensionValue.
    Direction: BusinessTerm -> Metric | DimensionValue."""

    confidence: float = 1.0


class RefersTo(BaseModel):
    """BusinessTerm references or is conceptually related to a Metric or DimensionValue
    without being a strict alias. Direction: BusinessTerm -> Metric | DimensionValue."""

    context: str = ""


class DefinedAs(BaseModel):
    """Metric has an authoritative prose definition captured in a BusinessDefinition.
    Direction: Metric -> BusinessDefinition."""

    effective_date: str = ""


class CalculatedBy(BaseModel):
    """Metric is computed using a specific KPIFormula expression.
    Direction: Metric -> KPIFormula."""

    expression: str = ""


class ScopedBy(BaseModel):
    """Metric is inherently partitioned or scoped along a Dimension axis.
    Direction: Metric -> Dimension."""

    scope_type: str = ""


class CanFilterBy(BaseModel):
    """Metric supports filtering by a given Dimension in WHERE clauses.
    Direction: Metric -> Dimension."""

    filter_type: str = ""


class ValidValueFor(BaseModel):
    """DimensionValue is a known valid member of a Dimension.
    Direction: DimensionValue -> Dimension."""

    is_default: bool = False


# ---------------------------------------------------------------------------
# Physical data edges
# ---------------------------------------------------------------------------


class BackedBy(BaseModel):
    """Metric is physically backed by a Table (the column details are embedded
    in the Table entity itself).
    Direction: Metric -> Table."""

    mapping_expression: str = ""


class AuthoritativeSourceFor(BaseModel):
    """Metric has a designated golden-source Table that is the canonical provider.
    Direction: Metric -> Table."""

    authority_level: str = ""


class BelongsTo(BaseModel):
    """Table is a member of a Dataset (schema / catalog).
    Direction: Table -> Dataset."""

    role: str = ""


class HasGrain(BaseModel):
    """Table is pre-aggregated at a specific AggregationGrain.
    Direction: Table -> AggregationGrain."""

    grain_description: str = ""


class JoinsTo(BaseModel):
    """Two Tables can be joined together in SQL.
    Direction: Table -> Table."""

    join_condition: str = ""
    join_type: str = "INNER"
    cardinality: str = ""


class Connects(BaseModel):
    """JoinPath links to the Tables it connects.
    Direction: JoinPath -> Table."""

    direction: str = ""


# ---------------------------------------------------------------------------
# Query edges
# ---------------------------------------------------------------------------


class Requests(BaseModel):
    """QueryIntent needs a specific Metric to answer the user question.
    Direction: QueryIntent -> Metric."""

    priority: str = ""


class GroupsBy(BaseModel):
    """QueryIntent uses a Dimension in its GROUP BY clause.
    Direction: QueryIntent -> Dimension."""

    order: int = 0


class FiltersBy(BaseModel):
    """QueryIntent applies a filter predicate on a Dimension.
    Direction: QueryIntent -> Dimension."""

    operator: str = ""
    default_value: str = ""


class UsesPattern(BaseModel):
    """QueryIntent is best answered by a specific SQLPattern template.
    Direction: QueryIntent -> SQLPattern."""

    confidence: float = 1.0


class Requires(BaseModel):
    """SQLPattern must satisfy a ConstraintRule before execution.
    Direction: SQLPattern -> ConstraintRule."""

    severity: str = "error"


class ValidatedBy(BaseModel):
    """SQLPattern output is checked by a ValidationRule after execution.
    Direction: SQLPattern -> ValidationRule."""

    check_type: str = ""


class ReturnsShape(BaseModel):
    """QueryIntent produces a result matching a specific ResultShape.
    Direction: QueryIntent -> ResultShape."""

    format_hint: str = ""


# ---------------------------------------------------------------------------
# Governance edges
# ---------------------------------------------------------------------------


class CanAccess(BaseModel):
    """UserRole is permitted to query a Metric or Table.
    Direction: UserRole -> Metric | Table."""

    permission_level: str = ""


class RestrictedBy(BaseModel):
    """Metric or Table has access governed by an AccessPolicy.
    Direction: Metric | Table -> AccessPolicy."""

    restriction_type: str = ""


class RefreshedUnder(BaseModel):
    """Metric data freshness is governed by a FreshnessPolicy.
    Direction: Metric -> FreshnessPolicy."""

    schedule: str = ""


class HasAuthority(BaseModel):
    """Table has a designated authoritative owner team via SourceAuthority.
    Direction: Table -> SourceAuthority."""

    authority_level: str = ""


# ---------------------------------------------------------------------------
# Learning / evolution edges
# ---------------------------------------------------------------------------


class Updated(BaseModel):
    """A DefinitionChange or PolicyChange has modified a Metric or AccessPolicy.
    Direction: DefinitionChange -> Metric | PolicyChange -> AccessPolicy."""

    changed_at: str = ""
    reason: str = ""


class ModifiedSchemaOf(BaseModel):
    """A SchemaChange has altered the DDL of a Table.
    Direction: SchemaChange -> Table."""

    change_type: str = ""
    changed_at: str = ""


class Exemplifies(BaseModel):
    """A UsageExample demonstrates how to answer a QueryIntent with real SQL.
    Direction: UsageExample -> QueryIntent."""

    relevance: float = 1.0


class CorrectedBy(BaseModel):
    """An AnalystFeedback provides a correction or improvement to a SQLPattern.
    Direction: AnalystFeedback -> SQLPattern."""

    correction_note: str = ""


class Invalidates(BaseModel):
    """A QueryFailureCase proves a SQLPattern produces incorrect results.
    Direction: QueryFailureCase -> SQLPattern."""

    reason: str = ""


class WarnsAbout(BaseModel):
    """A QueryFailureCase flags a SQLPattern as risky but not fully invalid.
    Direction: QueryFailureCase -> SQLPattern."""

    severity: str = "warning"


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

EDGE_TYPES: dict[str, type[BaseModel]] = {
    "ALIAS_OF": AliasOf,
    "REFERS_TO": RefersTo,
    "DEFINED_AS": DefinedAs,
    "CALCULATED_BY": CalculatedBy,
    "SCOPED_BY": ScopedBy,
    "CAN_FILTER_BY": CanFilterBy,
    "VALID_VALUE_FOR": ValidValueFor,
    "BACKED_BY": BackedBy,
    "AUTHORITATIVE_SOURCE_FOR": AuthoritativeSourceFor,
    "BELONGS_TO": BelongsTo,
    "HAS_GRAIN": HasGrain,
    "JOINS_TO": JoinsTo,
    "CONNECTS": Connects,
    "REQUESTS": Requests,
    "GROUPS_BY": GroupsBy,
    "FILTERS_BY": FiltersBy,
    "USES_PATTERN": UsesPattern,
    "REQUIRES": Requires,
    "VALIDATED_BY": ValidatedBy,
    "RETURNS_SHAPE": ReturnsShape,
    "CAN_ACCESS": CanAccess,
    "RESTRICTED_BY": RestrictedBy,
    "REFRESHED_UNDER": RefreshedUnder,
    "HAS_AUTHORITY": HasAuthority,
    "UPDATED": Updated,
    "MODIFIED_SCHEMA_OF": ModifiedSchemaOf,
    "EXEMPLIFIES": Exemplifies,
    "CORRECTED_BY": CorrectedBy,
    "INVALIDATES": Invalidates,
    "WARNS_ABOUT": WarnsAbout,
}

EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    ("BusinessTerm", "Metric"): ["ALIAS_OF", "REFERS_TO"],
    ("BusinessTerm", "DimensionValue"): ["ALIAS_OF", "REFERS_TO"],
    ("Metric", "BusinessDefinition"): ["DEFINED_AS"],
    ("Metric", "KPIFormula"): ["CALCULATED_BY"],
    ("Metric", "Dimension"): ["SCOPED_BY", "CAN_FILTER_BY"],
    ("DimensionValue", "Dimension"): ["VALID_VALUE_FOR"],
    ("Metric", "Table"): ["AUTHORITATIVE_SOURCE_FOR", "BACKED_BY"],
    ("Table", "Dataset"): ["BELONGS_TO"],
    ("Table", "AggregationGrain"): ["HAS_GRAIN"],
    ("Table", "Table"): ["JOINS_TO"],
    ("JoinPath", "Table"): ["CONNECTS"],
    ("QueryIntent", "Metric"): ["REQUESTS"],
    ("QueryIntent", "Dimension"): ["GROUPS_BY", "FILTERS_BY"],
    ("QueryIntent", "SQLPattern"): ["USES_PATTERN"],
    ("SQLPattern", "ConstraintRule"): ["REQUIRES"],
    ("SQLPattern", "ValidationRule"): ["VALIDATED_BY"],
    ("QueryIntent", "ResultShape"): ["RETURNS_SHAPE"],
    ("UserRole", "Metric"): ["CAN_ACCESS"],
    ("UserRole", "Table"): ["CAN_ACCESS"],
    ("Metric", "AccessPolicy"): ["RESTRICTED_BY"],
    ("Table", "AccessPolicy"): ["RESTRICTED_BY"],
    ("Metric", "FreshnessPolicy"): ["REFRESHED_UNDER"],
    ("Table", "SourceAuthority"): ["HAS_AUTHORITY"],
    ("DefinitionChange", "Metric"): ["UPDATED"],
    ("SchemaChange", "Table"): ["MODIFIED_SCHEMA_OF"],
    ("PolicyChange", "AccessPolicy"): ["UPDATED"],
    ("UsageExample", "QueryIntent"): ["EXEMPLIFIES"],
    ("AnalystFeedback", "SQLPattern"): ["CORRECTED_BY"],
    ("QueryFailureCase", "SQLPattern"): ["INVALIDATES", "WARNS_ABOUT"],
}
