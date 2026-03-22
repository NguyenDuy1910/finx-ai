"""pipeline.schemas — Pydantic models for the canonical document format.

This is the single source of truth for the preprocessing pipeline's data
contract. Every adapter, extractor, normalizer, and writer operates on these
types.
"""

from .blocks import (
    BlockProvenance,
    BlockType,
    ChartBlock,
    CodeBlock,
    ContentBlock,
    DiagramBlock,
    HeadingBlock,
    ImageBlock,
    KeyValueBlock,
    LinkRef,
    ListBlock,
    SectionNode,
    TableBlock,
    TextBlock,
)
from .canonical import CanonicalDocument
from .chunk import ChunkDocument, ChunkKind
from .provenance import ProcessingStage, ProcessingStep, Provenance, QualitySignal

__all__ = [
    "BlockProvenance",
    "BlockType",
    "CanonicalDocument",
    "ChartBlock",
    "ChunkDocument",
    "ChunkKind",
    "CodeBlock",
    "ContentBlock",
    "DiagramBlock",
    "HeadingBlock",
    "ImageBlock",
    "KeyValueBlock",
    "LinkRef",
    "ListBlock",
    "ProcessingStage",
    "ProcessingStep",
    "Provenance",
    "QualitySignal",
    "SectionNode",
    "TableBlock",
    "TextBlock",
]
