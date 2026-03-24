"""Document and content deduplication.

Pure functions operating on RetrievedDocument lists — no external deps.
"""

from __future__ import annotations

from typing import Any, List

from src.core.models.retrieval import RetrievedDocument

_CONTENT_DEDUP_THRESHOLD = 0.6


def deduplicate_hits_by_doc(hits: List[Any], max_per_doc: int = 3) -> List[Any]:
    """Limit raw Qdrant hits to *max_per_doc* per doc_id (pre-rerank)."""
    doc_counts: dict[str, int] = {}
    result: list[Any] = []
    for hit in hits:
        doc_id = (hit.payload or {}).get("doc_id", str(hit.id))
        count = doc_counts.get(doc_id, 0)
        if count < max_per_doc:
            result.append(hit)
            doc_counts[doc_id] = count + 1
    return result


def deduplicate_by_content(
    docs: List[RetrievedDocument],
    threshold: float = _CONTENT_DEDUP_THRESHOLD,
) -> List[RetrievedDocument]:
    """Remove near-duplicate documents by word-level Jaccard similarity.

    For same-doc pairs the threshold applies as-is; cross-doc pairs need
    a higher overlap (0.8) to be removed.
    """
    if len(docs) <= 1:
        return docs

    keep: list[RetrievedDocument] = []
    for doc in docs:
        is_dup = False
        for kept in keep:
            sim = _jaccard_words(doc.content, kept.content)
            if sim > threshold:
                doc_id = doc.meta_data.get("doc_id", "")
                kept_id = kept.meta_data.get("doc_id", "")
                if doc_id == kept_id:
                    is_dup = True
                    break
                if sim > 0.8:
                    is_dup = True
                    break
        if not is_dup:
            keep.append(doc)
    return keep


def _jaccard_words(a: str, b: str) -> float:
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
