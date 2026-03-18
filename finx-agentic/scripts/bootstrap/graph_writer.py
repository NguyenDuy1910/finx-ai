from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.knowledge.graph.client import FalkorDBClient
from src.knowledge.graph.extractor import Extractor
from src.core.llm import create_llm_adapter
from src.knowledge.graph.merger import Merger
from src.knowledge.graph.models import Chunk
from src.knowledge.graph.pipeline import GraphPipeline
from src.knowledge.graph.schema import setup_schema
from src.knowledge.graph.store import GraphStore

from .settings import BootstrapSettings

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    nodes_upserted: int = 0
    edges_upserted: int = 0
    chunks_extracted: int = 0
    chunks_failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    _start_time: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time

    def summary(self) -> str:
        lines = [
            "",
            "=" * 60,
            "Bootstrap Pipeline Summary",
            "=" * 60,
            f"  Elapsed time        : {self.elapsed_seconds:.1f}s",
            f"  Total nodes upserted: {self.nodes_upserted}",
            f"  Total edges upserted: {self.edges_upserted}",
            f"  Chunks extracted    : {self.chunks_extracted}",
            f"  Chunks failed       : {self.chunks_failed}",
        ]
        if self.errors:
            lines.append(f"  Errors recorded     : {len(self.errors)}")
        lines.append("=" * 60)
        return "\n".join(lines)


class GraphWriter:
    def __init__(self, settings: BootstrapSettings) -> None:
        self._client = FalkorDBClient(
            host=settings.falkordb_host,
            port=settings.falkordb_port,
            graph_name=settings.falkordb_graph,
        )
        self._store = GraphStore(self._client)

        llm = create_llm_adapter(
            provider="openai",
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url if settings.llm_base_url != "https://api.openai.com/v1" else None,
        )
        logger.info("LLM: base_url=%s  model=%s", settings.llm_base_url, settings.llm_model)

        extractor = Extractor(
            llm,
            gleaning_rounds=0,
            max_concurrent=5,
            max_tokens=settings.llm_max_tokens,
        )
        merger = Merger(self._store, llm=llm)
        self._pipeline = GraphPipeline(self._store, extractor, merger)
        self.stats = PipelineStats()

    def initialize(self) -> None:
        logger.info("Setting up FalkorDB schema...")
        setup_schema(self._client)

    def close(self) -> None:
        self._client.close()

    @property
    def graph_stats(self) -> dict[str, Any]:
        return self._store.stats()

    def extract_and_upsert(self, chunks: list[Chunk], batch_size: int = 20) -> None:
        if not chunks:
            return
        result = asyncio.run(self._pipeline.run(chunks))
        self.stats.nodes_upserted += result.nodes_upserted
        self.stats.edges_upserted += result.edges_upserted
        self.stats.chunks_extracted += result.total_chunks - len(result.errors)
        self.stats.chunks_failed += len(result.errors)
        for err in result.errors:
            self._record_error("pipeline", "batch", err)

    def flush_errors(self, path: Path) -> None:
        if not self.stats.errors:
            return
        with path.open("a", encoding="utf-8") as f:
            for err in self.stats.errors:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
        logger.info("Wrote %d errors to %s", len(self.stats.errors), path)

    def _record_error(self, stage: str, entity: str, reason: str) -> None:
        self.stats.errors.append({
            "stage": stage,
            "entity": entity,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def create_writer(settings: BootstrapSettings) -> GraphWriter:
    writer = GraphWriter(settings)
    writer.initialize()
    return writer
