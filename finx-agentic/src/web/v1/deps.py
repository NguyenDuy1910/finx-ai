from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from src.core.graph.client import GraphitiClient

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

logger = logging.getLogger(__name__)


class AppState:
    """Application-wide singleton state holding shared service clients."""

    def __init__(self) -> None:
        self._client: Optional[GraphitiClient] = None
        self._qdrant_wrapper: Optional["_QdrantRef"] = None

    @property
    def client(self) -> GraphitiClient:
        if self._client is None:
            self._client = GraphitiClient(
                host=os.getenv("FALKORDB_HOST", "localhost"),
                port=int(os.getenv("FALKORDB_PORT", "6379")),
            )
        return self._client

    @property
    def qdrant(self) -> "AsyncQdrantClient":
        """Shared async Qdrant client for knowledge retrieval."""
        from src.providers.qdrant import QdrantClient

        return QdrantClient.get_instance().async_client

    @property
    def default_database(self) -> str:
        return os.getenv("ATHENA_DATABASE", "")

    async def initialize(self) -> None:
        try:
            await self.client.initialize()
            logger.info("Graph initialized")
        except Exception as e:
            logger.warning("Graph initialization failed: %s", e)

    async def shutdown(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
        from src.providers.qdrant import QdrantClient

        try:
            await QdrantClient.get_instance().close()
        except Exception:
            pass


_state: Optional[AppState] = None


def get_app_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state
