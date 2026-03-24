from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_client: Any = None


def _get_openai() -> Any:
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI()
    return _client


class Embedder:
    """Thin embedding facade.  Caches vectors per query string within a session."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self._cache: dict[str, list[float]] = {}

    async def embed(self, text: str) -> list[float]:
        key = text.strip()
        if key in self._cache:
            return self._cache[key]
        client = _get_openai()
        response = await client.embeddings.create(input=[text], model=self._model)
        vector = response.data[0].embedding
        self._cache[key] = vector
        return vector
