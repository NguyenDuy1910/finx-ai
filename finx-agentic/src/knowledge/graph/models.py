from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Graph labels ───────────────────────────────────────────────────────────────

class NodeLabel(str, Enum):

    # Physical layer
    TABLE = "Table"
    DATASET = "Dataset"
    COLUMN = "Column"

    # Semantic layer
    BUSINESS_TERM = "BusinessTerm"
    METRIC = "Metric"
    DIMENSION = "Dimension"

    # Governance / provenance layer
    SOURCE_AUTHORITY = "SourceAuthority"
    USER_ROLE = "UserRole"

    # Auto-discovered by LLM (catch-all for new types)
    CONCEPT = "Concept"


class EdgeType(str, Enum):
    """Allowed relationship types in FalkorDB.  Keep in sync with schema.py indexes."""

    BELONGS_TO = "BELONGS_TO"              # Table → Dataset
    HAS_COLUMN = "HAS_COLUMN"              # Table → Column
    BACKED_BY = "BACKED_BY"                # BusinessTerm/Metric → SourceAuthority
    REFERS_TO = "REFERS_TO"                # Column/BusinessTerm → BusinessTerm/Metric
    ALIAS_OF = "ALIAS_OF"                  # any → any (synonym link)
    RELATED_TO = "RELATED_TO"              # LLM-discovered generic
    DEFINED_AS = "DEFINED_AS"              # Metric → BusinessTerm
    OWNED_BY = "OWNED_BY"                  # Table/Dataset → UserRole
    JOINS_WITH = "JOINS_WITH"              # Table → Table
    PART_OF = "PART_OF"                    # Dimension → BusinessTerm


# ── Graph property containers ──────────────────────────────────────────────────

GRAPH_FIELD_SEP = "<SEP>"
"""Separator used for multi-value string fields stored in FalkorDB properties."""


@dataclass
class NodeData:
    """Properties to persist on a graph node."""

    name: str
    label: str                               # NodeLabel.value
    description: str = ""
    domain: str = ""
    synonyms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    file_path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    # ── helpers ────────────────────────────────────────────────────────────

    @property
    def node_id(self) -> str:
        """Canonical unique identifier: UPPER(name)."""
        return self.name.upper().strip()

    def to_props(self) -> dict[str, Any]:
        """Flat dict ready for FalkorDB ``SET n += $props``."""
        props: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "domain": self.domain,
            "synonyms": GRAPH_FIELD_SEP.join(self.synonyms) if self.synonyms else "",
            "tags": GRAPH_FIELD_SEP.join(self.tags) if self.tags else "",
            "source_ids": GRAPH_FIELD_SEP.join(self.source_ids) if self.source_ids else "",
            "file_path": self.file_path,
        }
        props.update(self.extra)
        return props

    @classmethod
    def from_props(cls, props: dict[str, Any]) -> NodeData:
        return cls(
            name=props.get("name", ""),
            label=props.get("label", ""),
            description=props.get("description", ""),
            domain=props.get("domain", ""),
            synonyms=_split_sep(props.get("synonyms", "")),
            tags=_split_sep(props.get("tags", "")),
            source_ids=_split_sep(props.get("source_ids", "")),
            file_path=props.get("file_path", ""),
            extra={
                k: v
                for k, v in props.items()
                if k not in {
                    "name", "label", "description", "domain",
                    "synonyms", "tags", "source_ids", "file_path",
                }
            },
        )


@dataclass
class EdgeData:

    src: str           # source node name
    tgt: str           # target node name
    edge_type: str     # EdgeType.value
    description: str = ""
    keywords: str = ""
    weight: float = 1.0
    source_ids: list[str] = field(default_factory=list)

    @property
    def edge_id(self) -> str:
        return f"{self.src.upper().strip()}|{self.edge_type}|{self.tgt.upper().strip()}"

    def to_props(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "keywords": self.keywords,
            "weight": self.weight,
            "source_ids": GRAPH_FIELD_SEP.join(self.source_ids) if self.source_ids else "",
        }

    @classmethod
    def from_props(cls, src: str, tgt: str, edge_type: str, props: dict[str, Any]) -> EdgeData:
        return cls(
            src=src,
            tgt=tgt,
            edge_type=edge_type,
            description=props.get("description", ""),
            keywords=props.get("keywords", ""),
            weight=float(props.get("weight", 1.0)),
            source_ids=_split_sep(props.get("source_ids", "")),
        )


# ── Pipeline data types ───────────────────────────────────────────────────────

@dataclass
class Chunk:
    """A unit of text sent to the LLM extractor."""

    id: str       # sha256 hash of content
    content: str         # text sent to LLM
    source_id: str       # e.g. "schema" | "confluence"
    file_path: str       # original file for provenance
    doc_id: str          # parent document identifier

    @staticmethod
    def make_id(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class RawNode:
    """Entity extracted by LLM (before merge)."""

    name: str
    entity_type: str     # should map to NodeLabel.value
    description: str
    source_id: str       # chunk id
    file_path: str = ""
    synonyms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def node_id(self) -> str:
        return self.name.upper().strip()


@dataclass
class RawEdge:
    """Relationship extracted by LLM (before merge)."""

    src: str
    tgt: str
    edge_type: str       # should map to EdgeType.value
    keywords: str = ""
    description: str = ""
    source_id: str = ""
    weight: float = 1.0


@dataclass
class ExtractionResult:
    """Output of a single chunk extraction pass."""

    nodes: dict[str, list[RawNode]] = field(default_factory=dict)
    """node_id → list of RawNode candidates (may come from gleaning)."""

    edges: dict[tuple[str, str], list[RawEdge]] = field(default_factory=dict)
    """(src_id, tgt_id) → list of RawEdge candidates."""

    chunk_id: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _split_sep(val: str | Any) -> list[str]:
    """Split a GRAPH_FIELD_SEP-delimited string, filtering blanks."""
    if not val or not isinstance(val, str):
        return []
    return [s.strip() for s in val.split(GRAPH_FIELD_SEP) if s.strip()]
