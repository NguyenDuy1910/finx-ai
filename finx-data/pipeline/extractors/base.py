"""Abstract base for content extractors.

Extractors convert ``RawDocument`` instances into ``CanonicalDocument``
by parsing structure (headings, tables, images, links) from raw content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.adapters.base import RawDocument
from pipeline.schemas.canonical import CanonicalDocument


class BaseExtractor(ABC):
    """Abstract extractor that converts raw content into structured blocks.

    Extractors are responsible for:
    - Parsing document structure (headings, tables, images, code blocks)
    - Building section hierarchy
    - Extracting links
    - Populating content_blocks on the CanonicalDocument
    - Recording a provenance step
    """

    name: str = "base"

    @abstractmethod
    def extract(self, raw: RawDocument) -> CanonicalDocument:
        """Parse a ``RawDocument`` into a ``CanonicalDocument``."""
        ...

    def can_handle(self, raw: RawDocument) -> bool:
        """Return True if this extractor can process the given raw document."""
        return True
