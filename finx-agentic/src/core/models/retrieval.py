from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RetrievalContext:
    """Deprecated: use ``src.models.RetrievalContext`` instead.

    Kept for backward compatibility with postprocess pipeline.
    """

    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    allowed_spaces: Optional[List[str]] = None
    language: Optional[str] = None
    source_types: Optional[List[str]] = None
    domain: Optional[str] = None
    document_type: Optional[str] = None
    space_key: Optional[str] = None
    session_anchors: Optional[List[Dict[str, Any]]] = None


@dataclass
class RetrievedDocument:

    name: str = ""
    content: str = ""
    meta_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Final output of the retrieval pipeline."""

    documents: List[RetrievedDocument] = field(default_factory=list)
    packed_refs: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    anchors: List[Dict[str, Any]] = field(default_factory=list)
    query_type: str = "general_knowledge"
    rewritten_query: str = ""
    skipped: bool = False
