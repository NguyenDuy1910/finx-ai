"""Abstract base for output writers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.schemas.canonical import CanonicalDocument


class BaseWriter(ABC):
    """Abstract writer that persists CanonicalDocuments to a destination."""

    name: str = "base"

    @abstractmethod
    def write(self, doc: CanonicalDocument) -> str:
        """Write a single document. Returns a path/URI of the written output."""
        ...

    def write_batch(self, docs: list[CanonicalDocument]) -> list[str]:
        """Write multiple documents. Returns paths/URIs."""
        return [self.write(doc) for doc in docs]

    def flush(self) -> None:
        """Flush any buffered writes."""
