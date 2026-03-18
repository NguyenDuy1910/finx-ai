"""Shared data models for the indexing package.

All dataclasses / enums that cross workflow boundaries live here so that
every workflow file can import from a single, stable location instead of
reaching into ``__init__.py`` or each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

EpisodePayload = dict[str, Any]


@dataclass
class PreparedItem:
    """A named source item with its episodes ready to write to Graphiti."""

    item_name: str
    episodes: list[EpisodePayload] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ingestion request / state
# ---------------------------------------------------------------------------


class IngestionInputType(str, Enum):
    FILE_BYTES = "file_bytes"
    URL = "url"
    TEXT = "text"
    CONFLUENCE = "confluence"


@dataclass(slots=True)
class IngestionRequest:
    """Describes a single piece of content to ingest (file, URL, text, Confluence)."""

    input_type: IngestionInputType
    source_name: str = ""
    source_type: Any = "raw_text"
    content_bytes: Optional[bytes] = None
    content_text: Optional[str] = None
    url: Optional[str] = None
    filename: str = "document"
    content_type: str = ""
    chunking_strategy: Any = None
    confluence_base_url: Optional[str] = None
    confluence_username: Optional[str] = None
    confluence_api_token: Optional[str] = None
    entity_name: str = ""
    tags: list[str] = field(default_factory=list)
    extra_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceSection:
    """One text chunk produced from an IngestionRequest, ready for LLM enrichment."""

    source_index: int
    source_name: str
    source_record_id: str
    source_type: str
    source_description: str
    reference_time: datetime
    section_index: int
    section_text: str
    entity_name: str
    tags: list[str]
    metadata: dict[str, Any]


@dataclass(slots=True)
class PreparedEpisode:
    """A Graphiti episode ready to be written, produced from a CanonicalEvent."""

    name: str
    episode_body: dict[str, Any] | str
    source: Any
    source_description: str
    reference_time: datetime
    group_id: str


@dataclass
class IngestionState:
    """Mutable state threaded through the document ingestion workflow steps."""

    requests: list[IngestionRequest]
    group_id: str
    source_system: str = "document_ingestion"

    sections: list[SourceSection] = field(default_factory=list)
    knowledge_sources: list[dict[str, Any]] = field(default_factory=list)

    extracted_events: list[Any] = field(default_factory=list)
    prepared_episodes: list[PreparedEpisode] = field(default_factory=list)

    errors: list[str] = field(default_factory=list)
