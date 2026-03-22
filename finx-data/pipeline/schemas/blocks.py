"""Content block types used inside a CanonicalDocument.

Each block represents a discrete piece of content with its own type,
structural position, and metadata. Blocks are the atomic units that
downstream systems (vector chunking, graph extraction) operate on.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    """Discriminator for content block types."""

    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    HEADING = "heading"
    LIST = "list"
    KEY_VALUE = "key_value"
    CHART = "chart"
    DIAGRAM = "diagram"


class TextBlock(BaseModel):
    """A contiguous run of paragraph text."""

    block_type: BlockType = BlockType.TEXT
    content: str = Field(..., description="Plain-text or markdown content")
    language: str | None = Field(
        None, description="ISO 639-1 language code if detected"
    )


class HeadingBlock(BaseModel):
    """A section heading with explicit level."""

    block_type: BlockType = BlockType.HEADING
    content: str
    level: int = Field(..., ge=1, le=6, description="Heading level 1–6")


class TableBlock(BaseModel):
    """A structured table extracted from a document.

    Tables are preserved in both raw markdown and parsed row/column form
    so downstream can choose the best representation.
    """

    block_type: BlockType = BlockType.TABLE
    markdown: str = Field("", description="Markdown representation of the table")
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    caption: str | None = None


class ImageBlock(BaseModel):
    """An image reference with optional extracted/described content."""

    block_type: BlockType = BlockType.IMAGE
    src: str = Field(..., description="URI or path to the image")
    alt_text: str = ""
    description: str = Field(
        "", description="LLM-generated or OCR description of the image"
    )
    mime_type: str | None = None


class CodeBlock(BaseModel):
    """A code snippet or SQL fragment."""

    block_type: BlockType = BlockType.CODE
    content: str
    language: str | None = Field(None, description="e.g. sql, python, json")


class ListBlock(BaseModel):
    """An ordered or unordered list."""

    block_type: BlockType = BlockType.LIST
    items: list[str] = Field(default_factory=list)
    ordered: bool = False


class KeyValueBlock(BaseModel):
    """Extracted key-value pairs (from forms, headers, metadata blocks)."""

    block_type: BlockType = BlockType.KEY_VALUE
    pairs: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {'key': ..., 'value': ...} dicts",
    )
    source_context: str = Field(
        "", description="Where the KV pairs were extracted from (form, header, etc.)"
    )


class ChartBlock(BaseModel):
    """A chart or graph extracted from a document."""

    block_type: BlockType = BlockType.CHART
    chart_type: str = Field("", description="bar, line, pie, scatter, etc.")
    title: str = ""
    axes: dict[str, str] = Field(
        default_factory=dict, description="e.g. {'x': 'Quarter', 'y': 'Revenue (USD)'}"
    )
    legend: list[str] = Field(default_factory=list)
    data_points: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Visible data values extracted from the chart",
    )
    trend_summary: str = Field(
        "", description="Brief description of the trend shown in the chart"
    )
    description: str = Field(
        "", description="Full textual description of the chart"
    )


class DiagramBlock(BaseModel):
    """A diagram (flowchart, architecture, org chart, etc.)."""

    block_type: BlockType = BlockType.DIAGRAM
    diagram_type: str = Field("", description="flowchart, architecture, sequence, org_chart, etc.")
    title: str = ""
    components: list[str] = Field(
        default_factory=list, description="Named components/nodes in the diagram"
    )
    relationships: list[str] = Field(
        default_factory=list,
        description="Edges/arrows as 'A -> B: label' strings",
    )
    description: str = Field(
        "", description="Full textual description of the diagram"
    )


class BlockProvenance(BaseModel):
    """Per-block provenance: tracks how a block was produced."""

    extractor: str = Field("", description="Name of the extractor that created this block")
    confidence: float = Field(
        1.0, ge=0.0, le=1.0, description="Extraction confidence (1.0 = deterministic parser)"
    )
    source_page: int | None = Field(None, description="PDF page number (1-based) if applicable")
    source_sheet: str | None = Field(None, description="Excel sheet name if applicable")
    warnings: list[str] = Field(default_factory=list)


class LinkRef(BaseModel):
    """A hyperlink extracted from document content."""

    url: str
    text: str = ""
    context: str = Field(
        "", description="Surrounding text where the link appeared"
    )


# Union of all content block types for use in CanonicalDocument
ContentBlock = (
    TextBlock | HeadingBlock | TableBlock | ImageBlock | CodeBlock
    | ListBlock | KeyValueBlock | ChartBlock | DiagramBlock
)


class SectionNode(BaseModel):
    """A node in the document's section hierarchy tree.

    Preserves the logical outline so downstream chunkers can split on
    section boundaries and graph extractors can assign scope.
    """

    title: str
    level: int = Field(..., ge=1, le=6)
    path: list[str] = Field(
        default_factory=list,
        description="Ancestor titles from root to this section, e.g. ['Chapter 1', 'Section 1.2']",
    )
    block_indices: list[int] = Field(
        default_factory=list,
        description="Indices into the parent document's content_blocks list",
    )
    children: list[SectionNode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
