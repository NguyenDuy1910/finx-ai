"""Step 3 — group raw hits by source.

Groups cleaned hits by (doc_id, section_id, file/table name) and selects
the best representative hit per group.  This collapses redundant hits from
the same document section into a single "source block" before expansion.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List

from src.core.models.retrieval import RetrievedDocument

log = logging.getLogger(__name__)

_CHUNK_KINDS_TABLE = frozenset(
    {"table_summary", "table_schema", "table_row_group", "schema_summary"}
)


@dataclass
class SourceGroup:
    """A cluster of hits from the same logical source."""

    key: str
    doc_id: str
    section_id: str
    source_label: str  # human-readable: doc title, file name, or table name
    hits: List[RetrievedDocument] = field(default_factory=list)

    @property
    def best_score(self) -> float:
        return max(
            (h.meta_data.get("boosted_score") or h.meta_data.get("qdrant_score") or 0.0
             for h in self.hits),
            default=0.0,
        )

    @property
    def best_hit(self) -> RetrievedDocument:
        return max(
            self.hits,
            key=lambda h: h.meta_data.get("boosted_score") or h.meta_data.get("qdrant_score") or 0.0,
        )


def group_by_source(
    docs: List[RetrievedDocument],
    *,
    max_groups: int = 10,
) -> List[SourceGroup]:
    """Group hits into source blocks.

    Grouping key priority:
      1. (doc_id, section_id)  — same section in a document
      2. (doc_id, table/file name) — same table/attachment
      3. (doc_id,) alone — catch-all
    """
    groups: Dict[str, SourceGroup] = OrderedDict()

    for doc in docs:
        meta = doc.meta_data
        key = _group_key(meta)

        if key not in groups:
            groups[key] = SourceGroup(
                key=key,
                doc_id=meta.get("doc_id", ""),
                section_id=meta.get("section_id", ""),
                source_label=_source_label(doc),
            )
        groups[key].hits.append(doc)

    # Sort groups by best score descending
    sorted_groups = sorted(groups.values(), key=lambda g: g.best_score, reverse=True)

    log.debug(
        "Grouper: %d hits → %d groups (keeping top %d)",
        len(docs), len(sorted_groups), min(len(sorted_groups), max_groups),
    )
    return sorted_groups[:max_groups]


def flatten_groups(groups: List[SourceGroup]) -> List[RetrievedDocument]:
    """Flatten groups back to a doc list, ordered by group rank then position."""
    result: list[RetrievedDocument] = []
    for group in groups:
        # Within a group, order by chunk_position for reading coherence
        sorted_hits = sorted(
            group.hits,
            key=lambda d: d.meta_data.get("chunk_position", 0),
        )
        result.extend(sorted_hits)
    return result


def _group_key(meta: Dict) -> str:
    doc_id = meta.get("doc_id", "")
    section_id = meta.get("section_id", "")
    chunk_kind = meta.get("chunk_kind", "")
    attachment_id = meta.get("attachment_id", "")

    # Table chunks: group by doc + table identity
    if chunk_kind in _CHUNK_KINDS_TABLE:
        table_key = attachment_id or meta.get("doc_title", "") or doc_id
        return f"table::{doc_id}::{table_key}"

    # Attachment/file chunks
    if attachment_id:
        return f"file::{doc_id}::{attachment_id}"

    # Section-level grouping
    if doc_id and section_id:
        return f"section::{doc_id}::{section_id}"

    # Fallback: doc-level
    return f"doc::{doc_id or 'unknown'}"


def _source_label(doc: RetrievedDocument) -> str:
    meta = doc.meta_data
    title = meta.get("doc_title", "")
    heading = meta.get("heading", "")
    if title and heading:
        return f"{title} > {heading}"
    return title or heading or meta.get("external_id", "") or "unknown"
