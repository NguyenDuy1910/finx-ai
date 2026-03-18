"""Abstract base for normalizers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.schemas.canonical import CanonicalDocument


class BaseNormalizer(ABC):
    """Abstract normalizer that enriches a CanonicalDocument via LLM or rules.

    Normalizers run AFTER extractors and are responsible for:
    - Semantic enrichment (entity detection, domain tagging, abbreviation expansion)
    - Quality improvement (fixing OCR errors, standardizing terms)
    - Metadata augmentation (language detection, domain classification)
    - Adding provenance steps
    """

    name: str = "base"

    @abstractmethod
    def normalize(self, doc: CanonicalDocument) -> CanonicalDocument:
        """Enrich and normalize a CanonicalDocument."""
        ...
