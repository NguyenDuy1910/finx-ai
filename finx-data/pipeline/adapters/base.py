"""Abstract base for source adapters.

Every source adapter yields ``RawDocument`` instances — the rawest
representation of a source item before any parsing or normalization.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator


@dataclass
class RawDocument:
    """The rawest unit ingested from a source system.

    This is what adapters produce and what extractors consume.
    """

    source_system: str
    source_uri: str
    source_id: str = ""
    title: str = ""
    raw_content: str = ""
    raw_html: str = ""
    binary_content: bytes | None = None
    mime_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def content_hash(self) -> str:
        """SHA-256 of raw_content for idempotency / change detection."""
        payload = self.raw_content or ""
        if self.binary_content:
            return hashlib.sha256(self.binary_content).hexdigest()
        return hashlib.sha256(payload.encode()).hexdigest()


class BaseAdapter(ABC):
    """Abstract source adapter.

    Subclasses implement ``fetch()`` which yields ``RawDocument`` instances.
    Adapters are responsible for:
    - Connecting to the source system
    - Paginating / listing available items
    - Fetching raw content
    - Populating source metadata

    They are NOT responsible for parsing, extracting, or normalizing.
    """

    source_system: str = "unknown"

    @abstractmethod
    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        """Yield raw documents from the source system."""
        ...

    def test_connection(self) -> bool:
        """Check if the source system is reachable. Override for API sources."""
        return True
