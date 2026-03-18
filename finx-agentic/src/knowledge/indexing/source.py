from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from src.knowledge.indexing import PreparedItem

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type[IndexingSource]] = {}


class IndexingSource(ABC):

    source_type: ClassVar[str]

    def __init_subclass__(cls, source_type: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if source_type is not None:
            cls.source_type = source_type
            _REGISTRY[source_type] = cls

    @abstractmethod
    async def prepare(self) -> list[PreparedItem]:
        """Convert source data into a list of PreparedItem for indexing."""


def get_source_class(source_type: str) -> type[IndexingSource]:
    """Return the IndexingSource class registered for ``source_type``."""
    try:
        return _REGISTRY[source_type]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown source_type={source_type!r}. Available: {available}"
        ) from None


def registered_source_types() -> list[str]:
    """Return all registered source type names."""
    return sorted(_REGISTRY)
