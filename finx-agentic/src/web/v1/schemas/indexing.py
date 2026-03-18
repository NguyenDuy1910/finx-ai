from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Existing schemas ──────────────────────────────────────────────────────────

class LLMCost(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0
    llm_calls: int = 0
    embedding_calls: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    breakdown: Dict[str, Any] = Field(default_factory=dict)


class ContextBlockRequest(BaseModel):
    name: str
    content: str


class IndexItemRequest(BaseModel):
    name: str = ""
    source_description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    context_blocks: List[ContextBlockRequest] = Field(default_factory=list)
    content: str = ""
    body: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)


class IndexRequest(BaseModel):
    """Dynamic indexing input from many sources.

    `items` is the preferred shape.
    `tables` is kept for backward compatibility with existing UI payloads.
    """

    items: List[IndexItemRequest] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)


class IndexResponse(BaseModel):
    status: str = "success"
    tables_indexed: int = 0
    tables_failed: int = 0
    graph_stats: Dict[str, int] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    llm_cost: LLMCost = Field(default_factory=LLMCost)


class ProgressResponse(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0
    current_table: str = ""
    status: str = "idle"
    percent: float = 0.0


class StatsResponse(BaseModel):
    table_count: int = 0
    product_area_count: int = 0
    domain_knowledge_count: int = 0
    edge_count: int = 0


class IndexedTablesResponse(BaseModel):
    tables: List[str] = Field(default_factory=list)
    count: int = 0


# ── Preview schemas ───────────────────────────────────────────────────────────


class PreviewColumnSchema(BaseModel):
    name: str
    data_type: str = "string"
    description: str = ""
    is_partition: bool = False
    is_primary_key: bool = False
    sample_values: List[str] = Field(default_factory=list)


class PreviewTableSchema(BaseModel):
    name: str
    database: str
    columns: List[PreviewColumnSchema] = Field(default_factory=list)
    description: str = ""
    location: str = ""
    storage_format: str = ""
    partition_keys: List[str] = Field(default_factory=list)
    row_count: Optional[int] = None

class KnowledgeSourceRequest(BaseModel):
    """A single external knowledge document for the /preview endpoint.

    Attributes:
        source_type: Origin/format — pdf_extract | confluence_page | url_content |
                     raw_text | table_schema
        source_name: Human-readable label (filename, page title, URL…)
        content: Pre-extracted plain text
    """
    source_type: str = "raw_text"
    source_name: str = ""
    content: str


class PreviewRequest(BaseModel):
    """Request body for the /preview endpoint.

    Supports two ways of providing external knowledge:

    * **knowledge_sources** — structured list of typed documents (preferred).
      Each item has ``source_type`` (pdf_extract | confluence_page | url_content |
      raw_text | table_schema), an optional ``source_name`` label, and ``content``.

    * **context_text** — legacy: a single plain-text string (kept for backward
      compatibility; treated as ``raw_text``).
    """
    table_schema: PreviewTableSchema
    context_tables: List[str] = Field(default_factory=list)
    # Structured multi-source documents (preferred)
    knowledge_sources: List[KnowledgeSourceRequest] = Field(default_factory=list)
    # Legacy plain-text fallback (merged as raw_text)
    context_text: str = ""


class PreviewColumnDesign(BaseModel):
    name: str
    data_type: str = ""
    description: str = ""
    ai_description: str = ""
    business_terms: List[str] = Field(default_factory=list)
    is_primary_key: bool = False
    is_foreign_key: bool = False
    column_type: str = ""
    foreign_key_ref: str = ""


class PreviewRelationship(BaseModel):
    source_table: str = ""
    target_table: str = ""
    relationship_type: str = ""
    source_column: str = ""
    target_column: str = ""
    description: str = ""


class KGNode(BaseModel):
    id: str
    label: str
    type: str = "table"
    description: str = ""


class KGEdge(BaseModel):
    source: str
    target: str
    label: str = ""
    type: str = "structural"


class PreviewResponse(BaseModel):
    """Response returned by the /preview endpoint."""
    name: str
    database: str
    description: str = ""
    ai_description: str = ""
    entity_name: str = ""
    domain: str = ""
    synonyms: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    enriched_columns: List[PreviewColumnDesign] = Field(default_factory=list)
    relationships: List[PreviewRelationship] = Field(default_factory=list)
    # Knowledge Graph
    kg_nodes: List[KGNode] = Field(default_factory=list)
    kg_edges: List[KGEdge] = Field(default_factory=list)
    # Cost metadata
    llm_cost: LLMCost = Field(default_factory=LLMCost)


class UploadContextResponse(BaseModel):
    text: str
    char_count: int = 0
    source_name: str = ""


class FetchUrlRequest(BaseModel):
    url: str
    confluence_base_url: Optional[str] = None
    confluence_username: Optional[str] = None
    confluence_api_token: Optional[str] = None


class FetchUrlResponse(BaseModel):
    text: str
    char_count: int = 0
    source_name: str = ""
    is_confluence: bool = False


class IngestFilesResponse(BaseModel):
    status: str
    chunks_produced: int = 0
    episodes_written: int = 0
    knowledge_sources_count: int = 0
    graph_stats: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class IngestUrlRequest(BaseModel):
    url: str
    entity_name: str = ""
    tags: List[str] = Field(default_factory=list)
    write_to_graph: bool = True
    confluence_base_url: Optional[str] = None
    confluence_username: Optional[str] = None
    confluence_api_token: Optional[str] = None


class IngestUrlResponse(BaseModel):
    status: str
    url: str
    chunks_produced: int = 0
    episodes_written: int = 0
    knowledge_sources_count: int = 0
    graph_stats: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class IngestTextRequest(BaseModel):
    text: str
    source_name: str = ""
    entity_name: str = ""
    tags: List[str] = Field(default_factory=list)
    write_to_graph: bool = True


class IngestTextResponse(BaseModel):
    status: str
    chunks_produced: int = 0
    episodes_written: int = 0
    knowledge_sources_count: int = 0
    graph_stats: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
