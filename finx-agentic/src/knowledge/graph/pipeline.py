from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .extractor import Extractor
from .merger import Merger
from .models import Chunk, ExtractionResult
from .store import GraphStore

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    total_chunks: int = 0
    nodes_upserted: int = 0
    edges_upserted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


class GraphPipeline:
    def __init__(
        self,
        store: GraphStore,
        extractor: Extractor,
        merger: Merger,
        *,
        batch_size: int = 50,
    ) -> None:
        self._store = store
        self._extractor = extractor
        self._merger = merger
        self._batch_size = batch_size

    async def run(self, chunks: list[Chunk]) -> PipelineResult:
        result = PipelineResult(total_chunks=len(chunks))

        extraction_results: list[ExtractionResult] = await self._extractor.aextract_batch(
            chunks,
            progress_callback=lambda done, total: logger.info(
                "Extraction progress: %d/%d", done, total
            ),
        )

        for i in range(0, len(extraction_results), self._batch_size):
            batch = extraction_results[i: i + self._batch_size]
            try:
                n, e = await self._flush_batch(batch)
                result.nodes_upserted += n
                result.edges_upserted += e
            except Exception as exc:
                msg = f"Batch flush {i}-{i + len(batch)} failed: {exc}"
                logger.error(msg)
                result.errors.append(msg)

        return result

    async def _flush_batch(self, results: list[ExtractionResult]) -> tuple[int, int]:
        all_raw_nodes = [n for r in results for nodes in r.nodes.values() for n in nodes]
        all_raw_edges = [e for r in results for edges in r.edges.values() for e in edges]

        node_data_list, edge_data_list = await self._merger.amerge_batch(
            all_raw_nodes, all_raw_edges
        )

        self._store.upsert_nodes_batch(node_data_list)
        self._store.upsert_edges_batch(edge_data_list)

        return len(node_data_list), len(edge_data_list)
