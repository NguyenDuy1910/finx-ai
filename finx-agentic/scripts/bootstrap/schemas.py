"""Pydantic models for raw finx-data/output JSON shapes."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator, field_validator


# ── Schema directory models ────────────────────────────────────────────────────

class ColumnMeta(BaseModel):
    entity_type: str = "Column"
    column_name: str
    table_name: str = ""
    data_type: str = ""
    description: str = ""
    is_nullable: bool = True
    is_primary_key: bool = False
    is_partition_key: bool = False
    sample_values: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("is_nullable", "is_primary_key", "is_partition_key", mode="before")
    @classmethod
    def _coerce_none_bool(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)


class GrainMeta(BaseModel):
    entity_type: str = "AggregationGrain"
    name: str = ""
    grain_columns: list[str] = Field(default_factory=list)
    time_granularity: str = ""
    description: str = ""


class TableMeta(BaseModel):
    entity_type: str = "Table"
    table_name: str
    database: str = ""
    dataset: str = ""
    description: str = ""
    ai_description: str = ""
    domain: str = ""
    tags: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    partition_keys: list[str] = Field(default_factory=list)
    row_count: int | None = None
    storage_format: str = ""
    certification_status: str = ""
    deprecation_status: str = ""
    relationships: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("storage_format", "certification_status", "deprecation_status",
                     "database", "dataset", "description", "ai_description", "domain",
                     mode="before")
    @classmethod
    def _coerce_none_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class DatasetMeta(BaseModel):
    """Flat Dataset file: {entity_type: Dataset, name, database, description, owner, tags}."""
    entity_type: str = "Dataset"
    name: str = ""
    database: str = ""
    description: str = ""
    owner: str = ""
    domain: str = ""
    tags: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class SemanticModelMeta(BaseModel):
    """Flat SemanticModel file."""
    entity_type: str = "SemanticModel"
    name: str = ""
    domain: str = ""
    description: str = ""
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class SchemaFile(BaseModel):
    """Parsed content of a single schema JSON file from finx-data/output/schema/.

    Handles multiple shapes:
      - {table_name, table:{...}, columns:[...], grains:[...]}  → Table (standard)
      - {entity_type: Dataset, name, ...}                       → Dataset (flat)
      - {entity_type: SemanticModel, ...}                       → SemanticModel (flat)
      - {table_name, columns:[...]}  (no table key)             → View/legacy table
    """

    table_name: str = ""
    table: TableMeta | None = None
    columns: list[ColumnMeta] = Field(default_factory=list)
    grains: list[GrainMeta] = Field(default_factory=list)
    # flat entity types
    dataset: DatasetMeta | None = None
    semantic_model: SemanticModelMeta | None = None
    # raw file path (set after load)
    file_path: str = ""

    @model_validator(mode="before")
    @classmethod
    def coerce_shapes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        et = data.get("entity_type", "")

        # Dataset flat file
        if et == "Dataset":
            return {"dataset": data, "file_path": data.get("file_path", "")}

        # SemanticModel flat file
        if et == "SemanticModel":
            return {"semantic_model": data, "file_path": data.get("file_path", "")}

        # View or legacy flat table: has table_name + columns but no "table" key
        if "table_name" in data and "table" not in data and et not in ("Table",):
            # Synthesise a minimal TableMeta from the flat structure
            data["table"] = {
                "entity_type": "Table",
                "table_name": data["table_name"],
                "database": data.get("database", ""),
                "dataset": data.get("dataset", ""),
                "description": data.get("description", ""),
                "ai_description": data.get("ai_description", ""),
                "domain": data.get("domain", ""),
                "tags": data.get("tags", []),
                "synonyms": data.get("synonyms", []),
                "partition_keys": data.get("partition_keys", []),
                "certification_status": data.get("certification_status", ""),
                "deprecation_status": data.get("deprecation_status", ""),
                "relationships": data.get("relationships", []),
            }
            return data

        # Standard nested table: coerce table_name from nested table if missing
        if not data.get("table_name") and data.get("table"):
            t = data["table"]
            data["table_name"] = t.get("table_name", "") if isinstance(t, dict) else ""
        return data

    @property
    def effective_domain(self) -> str:
        if self.table:
            return (self.table.domain or "").lower().strip()
        return ""

    @property
    def effective_description(self) -> str:
        if not self.table:
            return ""
        parts: list[str] = []
        if self.table.description:
            parts.append(self.table.description)
        if self.table.ai_description and self.table.ai_description != self.table.description:
            parts.append(self.table.ai_description)
        return " | ".join(parts)

    def top_columns(self, max_n: int = 5) -> list[ColumnMeta]:
        """PK + partition columns first, then columns with non-empty descriptions, capped at max_n."""
        priority: list[ColumnMeta] = []
        rest: list[ColumnMeta] = []
        for c in self.columns:
            if c.is_primary_key or c.is_partition_key:
                priority.append(c)
            elif c.description.strip():
                rest.append(c)
        seen: set[str] = set()
        result: list[ColumnMeta] = []
        for c in priority + rest:
            if c.column_name not in seen:
                seen.add(c.column_name)
                result.append(c)
            if len(result) >= max_n:
                break
        return result


# ── Confluence directory models ────────────────────────────────────────────────

class ConfluenceItem(BaseModel):
    """A single structured entity extracted from a Confluence page."""

    entity_type: str
    name: str = ""
    # BusinessTerm fields
    domain: str = ""
    description: str = ""
    definition: str = ""
    synonyms: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # SourceAuthority fields
    authority_level: str = ""
    owner_team: str = ""
    # UserRole fields
    role_name: str = ""
    permissions: list[str] = Field(default_factory=list)
    notes: str = ""
    # Table fields (confluence-sourced)
    table_name: str = ""
    ai_description: str = ""
    partition_keys: list[str] = Field(default_factory=list)
    # Provenance
    source_document: str = ""
    source_url: str = ""
    relationships: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or self.table_name or self.role_name or ""

    @property
    def effective_definition(self) -> str:
        parts = []
        if self.definition:
            parts.append(self.definition)
        if self.description and self.description != self.definition:
            parts.append(self.description)
        return " | ".join(parts)


class ConfluenceFile(BaseModel):
    """Parsed content of a single Confluence JSON file from finx-data/output/confluence/."""

    page_id: str = ""
    title: str = ""
    url: str = ""
    space: str = ""
    items: list[ConfluenceItem] = Field(default_factory=list)
    file_path: str = ""

    @property
    def is_structured(self) -> bool:
        """True if this page has at least one typed item that maps to an ontology entity."""
        structured_types = {"BusinessTerm", "SourceAuthority", "UserRole", "Table"}
        return any(item.entity_type in structured_types for item in self.items)
