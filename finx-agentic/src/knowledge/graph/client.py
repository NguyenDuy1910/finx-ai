from __future__ import annotations

import logging
import os
from typing import Any

from falkordb import FalkorDB as _FalkorDB, Graph

from .exceptions import GraphConnectionError

logger = logging.getLogger(__name__)

DEFAULT_GRAPH_NAME = "finx_knowledge"


class FalkorDBClient:

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        graph_name: str | None = None,
    ) -> None:
        self._host = host or os.getenv("FALKORDB_HOST", "localhost")
        self._port = port or int(os.getenv("FALKORDB_PORT", "6379"))
        self._graph_name = graph_name or os.getenv("FALKORDB_GRAPH", DEFAULT_GRAPH_NAME)
        self._db: _FalkorDB | None = None
        self._graph: Graph | None = None

    # ── connection ─────────────────────────────────────────────────────────

    @property
    def graph(self) -> Graph:
        """Lazily connect and return the ``Graph`` handle."""
        if self._graph is None:
            try:
                self._db = _FalkorDB(host=self._host, port=self._port)
                self._graph = self._db.select_graph(self._graph_name)
                logger.info(
                    "FalkorDB connected: %s:%s graph=%s",
                    self._host, self._port, self._graph_name,
                )
            except Exception as exc:
                raise GraphConnectionError(self._host, self._port, exc) from exc
        return self._graph

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def graph_name(self) -> str:
        return self._graph_name

    # ── query execution ────────────────────────────────────────────────────

    def execute(self, query: str, params: dict[str, Any] | None = None) -> Any:
        logger.debug("Cypher: %s | params=%s", query[:200], params)
        return self.graph.query(query, params=params)

    async def aexecute(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return self.execute(query, params)

    # ── lifecycle ──────────────────────────────────────────────────────────

    def close(self) -> None:
        self._graph = None
        if self._db is not None:
            try:
                self._db.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._db = None
            logger.info("FalkorDB connection closed.")

    def __repr__(self) -> str:
        return f"FalkorDBClient({self._host}:{self._port}/{self._graph_name})"
