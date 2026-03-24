"""Centralised async Qdrant client with lazy singleton support."""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


class QdrantClient:
    """Async Qdrant client with lazy singleton support.

    Usage as singleton::

        client = QdrantClient.get_instance()
        raw = client.async_client          # underlying AsyncQdrantClient

    Usage as async context-manager::

        async with QdrantClient(url=...) as raw_client:
            await raw_client.scroll(...)
    """

    _instance: QdrantClient | None = None

    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        self.url = url or os.environ.get("QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.environ.get("QDRANT_API_KEY")
        self._client: Any | None = None

    # ── singleton ────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls, url: str | None = None, api_key: str | None = None) -> QdrantClient:
        if cls._instance is None:
            cls._instance = cls(url=url, api_key=api_key)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ── underlying async client (lazy) ───────────────────────────────

    @property
    def async_client(self) -> Any:
        if self._client is None:
            from qdrant_client import AsyncQdrantClient

            self._client = AsyncQdrantClient(url=self.url, api_key=self.api_key)
            log.info("Qdrant client initialised: %s", self.url)
        return self._client

    # ── lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            log.info("Qdrant client closed: %s", self.url)
            self._client = None

    async def __aenter__(self) -> Any:
        return self.async_client

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # ── helpers ──────────────────────────────────────────────────────

    async def check_sparse_support(self, collection_name: str) -> bool:
        """Return True when the collection advertises a named 'sparse' vector."""
        try:
            info = await self.async_client.get_collection(collection_name)
            vectors_config = info.config.params.vectors
            return isinstance(vectors_config, dict) and "sparse" in vectors_config
        except Exception:
            return False


# ── module-level convenience helpers ─────────────────────────────────


def get_qdrant_client(
    url: str | None = None,
    api_key: str | None = None,
) -> Any:
    """Return the singleton's underlying ``AsyncQdrantClient``."""
    return QdrantClient.get_instance(url=url, api_key=api_key).async_client


async def check_sparse_support(collection_name: str) -> bool:
    return await QdrantClient.get_instance().check_sparse_support(collection_name)
