from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agno.knowledge.document.base import Document

log = logging.getLogger("finx-agentic.reranker")

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class DocumentReranker:

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        *,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model: Any = None  # lazy-loaded

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            log.info("Loading reranker model: %s", self._model_name)
            self._model = CrossEncoder(self._model_name, device=self._device)
            log.info("Reranker ready.")
        except Exception as exc:
            log.warning(
                "Could not load CrossEncoder '%s': %s. Reranking disabled — "
                "returning docs in original retrieval order.",
                self._model_name,
                exc,
            )
            self._model = None

    def rerank(
        self,
        query: str,
        docs: list["Document"],
        top_n: int = 5,
    ) -> list["Document"]:
        """Score (query, doc.content) pairs and return top_n docs by score.

        The score is stored in each doc's meta_data["rerank_score"] for
        downstream debugging and logging.

        If the model failed to load, docs are returned unchanged (up to top_n).
        """
        if not docs:
            return []

        self._load()

        if self._model is None:
            # Graceful fallback — no reranking
            return docs[:top_n]

        pairs = [(query, d.content or "") for d in docs]
        try:
            scores: list[float] = self._model.predict(pairs).tolist()
        except Exception as exc:
            log.warning("Reranker prediction failed: %s. Using original order.", exc)
            return docs[:top_n]

        # Attach score to each doc's meta_data
        for doc, score in zip(docs, scores):
            if doc.meta_data is None:
                doc.meta_data = {}
            doc.meta_data["rerank_score"] = round(float(score), 4)

        ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        result = [doc for _, doc in ranked[:top_n]]

        log.debug(
            "Reranked %d docs → top %d | scores: %s",
            len(docs),
            top_n,
            [round(s, 3) for s, _ in ranked[:top_n]],
        )
        return result
