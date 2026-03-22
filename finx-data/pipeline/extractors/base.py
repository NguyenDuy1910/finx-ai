"""Abstract base for content extractors and shared utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.adapters.base import RawDocument
from pipeline.schemas.blocks import ContentBlock, HeadingBlock, SectionNode
from pipeline.schemas.canonical import CanonicalDocument


class BaseExtractor(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, raw: RawDocument) -> CanonicalDocument: ...

    def can_handle(self, raw: RawDocument) -> bool:
        return True


def assess_quality(blocks: list[ContentBlock]) -> "QualitySignal":
    """Assess extraction quality from content blocks."""
    from pipeline.schemas.provenance import QualitySignal

    has_tables = any(hasattr(b, "headers") for b in blocks)
    has_images = any(hasattr(b, "src") for b in blocks)
    has_code = any(hasattr(b, "language") and hasattr(b, "content") and not hasattr(b, "level") for b in blocks)
    word_count = sum(
        len(getattr(b, "content", "").split())
        for b in blocks
        if hasattr(b, "content")
    )
    return QualitySignal(
        has_tables=has_tables,
        has_images=has_images,
        has_code=has_code,
        word_count=word_count,
    )


def build_sections(blocks: list[ContentBlock]) -> list[SectionNode]:
    """Build section hierarchy from heading blocks."""
    sections: list[SectionNode] = []
    current_path: list[str] = []
    for i, block in enumerate(blocks):
        if isinstance(block, HeadingBlock):
            while current_path and len(current_path) >= block.level:
                current_path.pop()
            current_path.append(block.content)
            sections.append(
                SectionNode(
                    title=block.content,
                    level=block.level,
                    path=list(current_path),
                    block_indices=[i],
                )
            )
        elif sections:
            sections[-1].block_indices.append(i)
    return sections
