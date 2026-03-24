"""Cross-encoder reranking.

Thin wrapper around a singleton ``CrossEncoder`` model.
Operates on ``RetrievedDocument`` and ``ExpandedBlock`` — no Agno imports.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List

from src.core.models.retrieval import RetrievedDocument

log = logging.getLogger(__name__)

_DEFAULT_MODEL = os.environ.get(
    "RERANKER_MODEL",
    "cross-encoder/mmarco-mMiniLMv2-L-12-H-384-v1",
)

# Module-level singleton — loaded once, shared across all pipeline instances.
_model: Any = None
_model_name: str = _DEFAULT_MODEL


def _load_model() -> Any:
    global _model, _model_name
    if _model is not None:
        return _model
    try:
        from sentence_transformers import CrossEncoder
        log.info("Loading reranker model: %s", _model_name)
        _model = CrossEncoder(_model_name, device="cpu")
        log.info("Reranker ready.")
    except Exception as exc:
        log.warning("Could not load CrossEncoder '%s': %s — reranking disabled.", _model_name, exc)
        _model = None
    return _model


def rerank(
    query: str,
    docs: List[RetrievedDocument],
    top_n: int = 5,
) -> List[RetrievedDocument]:
    """Score ``(query, doc.content)`` pairs and return *top_n* by score.

    Attaches ``rerank_score`` to each document's ``meta_data``.
    Falls back to ``boosted_score`` ordering when the model is unavailable.
    """
    if not docs:
        return []

    model = _load_model()
    if model is None:
        return _fallback(docs, top_n)

    pairs = [(query, d.content) for d in docs]
    try:
        scores: list[float] = model.predict(pairs).tolist()
    except Exception as exc:
        log.warning("Reranker prediction failed: %s. Using fallback.", exc)
        return _fallback(docs, top_n)

    for doc, score in zip(docs, scores):
        doc.meta_data["rerank_score"] = round(float(score), 4)

    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    result = [doc for _, doc in ranked[:top_n]]

    log.debug(
        "Reranked %d → top %d | scores: %s",
        len(docs), top_n, [round(s, 3) for s, _ in ranked[:top_n]],
    )
    return result


def rerank_blocks(
    query: str,
    blocks: List[Any],  # List[ExpandedBlock]
    top_n: int = 6,
) -> List[Any]:
    """Rerank expanded context blocks by their merged content.

    Scores ``(query, block.content)`` and returns *top_n* blocks sorted
    by rerank score.  Each block's ``best_hit_score`` is updated to the
    rerank score.  Falls back to original ``best_hit_score`` ordering.
    """
    if not blocks:
        return []

    model = _load_model()
    if model is None:
        # Fallback: sort by original best_hit_score
        ranked = sorted(blocks, key=lambda b: b.best_hit_score, reverse=True)
        return ranked[:top_n]

    pairs = [(query, b.content) for b in blocks]
    try:
        scores: list[float] = model.predict(pairs).tolist()
    except Exception as exc:
        log.warning("Block reranker failed: %s. Using score fallback.", exc)
        ranked = sorted(blocks, key=lambda b: b.best_hit_score, reverse=True)
        return ranked[:top_n]

    for block, score in zip(blocks, scores):
        block.best_hit_score = round(float(score), 4)
        # Also propagate to underlying chunks
        for chunk in block.chunks:
            chunk.meta_data["rerank_score"] = round(float(score), 4)

    ranked = sorted(zip(scores, blocks), key=lambda x: x[0], reverse=True)
    result = [block for _, block in ranked[:top_n]]

    log.debug(
        "Reranked %d blocks → top %d | scores: %s",
        len(blocks), top_n, [round(s, 3) for s, _ in ranked[:top_n]],
    )
    return result


def _fallback(docs: List[RetrievedDocument], top_n: int) -> List[RetrievedDocument]:
    scored = []
    for doc in docs:
        s = doc.meta_data.get("boosted_score") or doc.meta_data.get("qdrant_score") or 0.0
        scored.append((float(s), doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    for s, doc in scored:
        doc.meta_data["rerank_score"] = round(s, 4)
    return [doc for _, doc in scored[:top_n]]
