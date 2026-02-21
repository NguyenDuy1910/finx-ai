from __future__ import annotations

import logging
import os
from typing import Optional

from src.knowledge.graph.client import GraphitiClient, get_graphiti_client
from src.knowledge.memory import MemoryManager

logger = logging.getLogger(__name__)


def _new_client() -> GraphitiClient:
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    return GraphitiClient(host=host, port=port)


class AppState:

    def __init__(self):
        self._client: Optional[GraphitiClient] = None
        self._memory: Optional[MemoryManager] = None

    @property
    def client(self) -> GraphitiClient:
        if self._client is None:
            self._client = _new_client()
        return self._client

    @property
    def memory(self) -> MemoryManager:
        if self._memory is None:
            self._memory = MemoryManager(self.client)
        return self._memory

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


_state: Optional[AppState] = None


def get_app_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state
