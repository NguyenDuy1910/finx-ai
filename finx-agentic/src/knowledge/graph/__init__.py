"""FalkorDB-backed knowledge graph — storage, models, schema, extraction, merge."""

from .client import FalkorDBClient
from .exceptions import GraphConnectionError, GraphError, NodeNotFoundError, EdgeNotFoundError
from .extractor import Extractor
from .merger import Merger
from .models import (
    Chunk,
    EdgeData,
    EdgeType,
    ExtractionResult,
    GRAPH_FIELD_SEP,
    NodeData,
    NodeLabel,
    RawEdge,
    RawNode,
)
from .prompts import (
    COMPLETION_DELIMITER,
    DESCRIPTION_SUMMARY,
    ENTITY_EXTRACTION_SYSTEM,
    ENTITY_EXTRACTION_USER,
    ENTITY_CONTINUE_EXTRACTION,
    TUPLE_DELIMITER,
)
from .schema import setup_schema
from .store import GraphStore

__all__ = [
    # client
    "FalkorDBClient",
    # store
    "GraphStore",
    "setup_schema",
    # extraction & merge
    "Extractor",
    "Merger",
    # models
    "NodeLabel",
    "EdgeType",
    "NodeData",
    "EdgeData",
    "Chunk",
    "RawNode",
    "RawEdge",
    "ExtractionResult",
    "GRAPH_FIELD_SEP",
    # prompts
    "TUPLE_DELIMITER",
    "COMPLETION_DELIMITER",
    "ENTITY_EXTRACTION_SYSTEM",
    "ENTITY_EXTRACTION_USER",
    "ENTITY_CONTINUE_EXTRACTION",
    "DESCRIPTION_SUMMARY",
    # exceptions
    "GraphError",
    "GraphConnectionError",
    "NodeNotFoundError",
    "EdgeNotFoundError",
]
