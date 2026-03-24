from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from src.models._helpers import clean_list


class SearchMode(str, Enum):
    HYBRID = "hybrid"
    VECTOR = "vector"
    KEYWORD = "keyword"
    EXACT = "exact"


class RetrievalIntent(str, Enum):
    QA = "qa"
    LOOKUP = "lookup"
    TABLE = "table"
    ATTACHMENT = "attachment"
    TICKET = "ticket"
    NAVIGATION = "navigation"


@dataclass(slots=True)
class ExpansionOptions:
    include_parent: bool = True
    include_children: bool = False
    include_neighbors: bool = True
    window_before: int = 1
    window_after: int = 1
    merge_table_family: bool = True
    include_attachment_parent: bool = True

    def __post_init__(self) -> None:
        if self.window_before < 0:
            raise ValueError("window_before must be >= 0")
        if self.window_after < 0:
            raise ValueError("window_after must be >= 0")

    @classmethod
    def disabled(cls) -> "ExpansionOptions":
        return cls(
            include_parent=False,
            include_children=False,
            include_neighbors=False,
            window_before=0,
            window_after=0,
            merge_table_family=False,
            include_attachment_parent=False,
        )


@dataclass(slots=True)
class QueryPlan:
    original_query: str
    rewritten_query: str

    search_mode: SearchMode | str = SearchMode.HYBRID
    intent: RetrievalIntent | str = RetrievalIntent.QA

    filters: dict[str, Any] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    requested_fields: list[str] = field(default_factory=list)

    top_k: int = 12
    candidate_k: int = 40
    rerank_k: int = 25
    min_score: float | None = None

    deduplicate_by_doc: bool = True
    expansion: ExpansionOptions = field(default_factory=ExpansionOptions)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.original_query = self.original_query.strip()
        self.rewritten_query = self.rewritten_query.strip() or self.original_query

        if not isinstance(self.search_mode, SearchMode):
            self.search_mode = SearchMode(str(self.search_mode).strip().lower())

        if not isinstance(self.intent, RetrievalIntent):
            self.intent = RetrievalIntent(str(self.intent).strip().lower())

        self.keywords = clean_list(self.keywords)
        self.entities = clean_list(self.entities)
        self.requested_fields = clean_list(self.requested_fields)
        self.notes = clean_list(self.notes)

        if self.top_k <= 0:
            raise ValueError("top_k must be > 0")
        if self.candidate_k <= 0:
            raise ValueError("candidate_k must be > 0")
        if self.rerank_k <= 0:
            raise ValueError("rerank_k must be > 0")
        if self.top_k > self.candidate_k:
            self.candidate_k = self.top_k
        if self.rerank_k > self.candidate_k:
            self.rerank_k = self.candidate_k
        if self.min_score is not None and self.min_score < 0:
            raise ValueError("min_score must be >= 0")

    @property
    def requires_rerank(self) -> bool:
        return self.search_mode in {SearchMode.HYBRID, SearchMode.VECTOR} and self.rerank_k > 1

    @property
    def is_exact_lookup(self) -> bool:
        return self.search_mode == SearchMode.EXACT or self.intent in {
            RetrievalIntent.LOOKUP,
            RetrievalIntent.TICKET,
        }

    def add_filter(self, key: str, value: Any) -> None:
        self.filters[key] = value

    def merge_filters(self, extra_filters: dict[str, Any] | None) -> None:
        if not extra_filters:
            return

        for key, value in extra_filters.items():
            if key not in self.filters:
                self.filters[key] = value
                continue

            current = self.filters[key]
            if isinstance(current, dict) and isinstance(value, dict):
                merged = dict(current)
                merged.update(value)
                self.filters[key] = merged
            else:
                self.filters[key] = value

    def add_note(self, note: str) -> None:
        note = note.strip()
        if note and note not in self.notes:
            self.notes.append(note)

    def clone_with(self, **changes: Any) -> "QueryPlan":
        return replace(self, **changes)

    def for_exact_lookup(self) -> "QueryPlan":
        return replace(
            self,
            search_mode=SearchMode.EXACT,
            rerank_k=1,
            expansion=ExpansionOptions.disabled(),
        )

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "search_mode": self.search_mode.value,
            "intent": self.intent.value,
            "filters": dict(self.filters),
            "keywords": list(self.keywords),
            "entities": list(self.entities),
            "requested_fields": list(self.requested_fields),
            "top_k": self.top_k,
            "candidate_k": self.candidate_k,
            "rerank_k": self.rerank_k,
            "min_score": self.min_score,
            "deduplicate_by_doc": self.deduplicate_by_doc,
            "expansion": {
                "include_parent": self.expansion.include_parent,
                "include_children": self.expansion.include_children,
                "include_neighbors": self.expansion.include_neighbors,
                "window_before": self.expansion.window_before,
                "window_after": self.expansion.window_after,
                "merge_table_family": self.expansion.merge_table_family,
                "include_attachment_parent": self.expansion.include_attachment_parent,
            },
            "notes": list(self.notes),
        }