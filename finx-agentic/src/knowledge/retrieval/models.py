"""Data classes used across the retrieval pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SearchResult:
    """A single search hit."""

    name: str
    label: str
    summary: str
    score: float
    attributes: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableContext:
    """Full context for a single table including columns, entities, joins, domain, rules and codesets."""

    table: str
    database: str
    description: str
    partition_keys: List[str] = field(default_factory=list)
    columns: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    related_tables: List[Dict[str, Any]] = field(default_factory=list)
    domain: Optional[str] = None
    business_rules: List[Dict[str, Any]] = field(default_factory=list)
    codesets: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaSearchResult:
    """Aggregated output of the multi-level search pipeline."""

    tables: List[SearchResult] = field(default_factory=list)
    columns: List[SearchResult] = field(default_factory=list)
    entities: List[SearchResult] = field(default_factory=list)
    patterns: List[Dict[str, Any]] = field(default_factory=list)
    context: List[Dict[str, Any]] = field(default_factory=list)
    # new fields from multi-level pipeline
    ranked_results: List[Dict[str, Any]] = field(default_factory=list)
    query_analysis: Optional[Dict[str, Any]] = None
    search_metadata: Dict[str, Any] = field(default_factory=dict)
