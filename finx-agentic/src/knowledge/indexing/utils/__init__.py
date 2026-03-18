"""Indexing utilities — pure helpers shared across all workflow files.

Import from here instead of reaching into individual sub-modules:

    from src.knowledge.indexing.utils import (
        split_sections, slugify, utc_now,          # text
        read_request_text,                         # readers
        infer_route, build_extraction_agent,       # events
        EpisodePayload, PreparedItem,              # models
        IngestionRequest, IngestionState,
    )
"""
from src.knowledge.indexing.utils.models import (
    EpisodePayload,
    PreparedItem,
    IngestionInputType,
    IngestionRequest,
    SourceSection,
    PreparedEpisode,
    IngestionState,
)
from src.knowledge.indexing.utils.text import (
    utc_now,
    slugify,
    split_sections,
)
from src.knowledge.indexing.utils.readers import (
    extract_document_text,
    read_file_bytes,
    read_url,
    read_request_text,
)
from src.knowledge.indexing.utils.events import (
    infer_route,
    build_system_prompt,
    normalize_source_type,
    normalize_episode_source,
    resolve_source_name,
    build_extraction_agent,
    parse_event_batch,
    normalize_event,
    event_to_episode,
)

__all__ = [
    # models
    "EpisodePayload",
    "PreparedItem",
    "IngestionInputType",
    "IngestionRequest",
    "SourceSection",
    "PreparedEpisode",
    "IngestionState",
    # text
    "utc_now",
    "slugify",
    "split_sections",
    # readers
    "extract_document_text",
    "read_file_bytes",
    "read_url",
    "read_request_text",
    # events
    "infer_route",
    "build_system_prompt",
    "normalize_source_type",
    "normalize_episode_source",
    "resolve_source_name",
    "build_extraction_agent",
    "parse_event_batch",
    "normalize_event",
    "event_to_episode",
]
