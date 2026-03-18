"""Qdrant ingestion pipeline — orchestrates load → embed → upsert."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .collection import CollectionManager
from .config import QdrantIngestConfig
from .embedder import EmbeddingProvider, OpenAIEmbedder
from .loader import KnowledgeLoader
from .payload import content_hash, doc_to_payload, doc_to_point_id, doc_to_text
from .upserter import QdrantUpserter

log = logging.getLogger("finx-data.ingest.pipeline")


@dataclass
class IngestResult:
    """Summary of a single ingestion run."""

    total_loaded: int = 0
    skipped_low_quality: int = 0
    skipped_unchanged: int = 0
    embedded: int = 0
    upserted: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def print_summary(self) -> None:
        log.info("=" * 60)
        log.info("Qdrant ingestion summary")
        log.info("  Total loaded       : %d", self.total_loaded)
        log.info("  Skipped (quality)  : %d", self.skipped_low_quality)
        log.info("  Skipped (unchanged): %d", self.skipped_unchanged)
        log.info("  Embedded           : %d", self.embedded)
        log.info("  Upserted           : %d", self.upserted)
        log.info("  Failed             : %d", self.failed)
        log.info("  Elapsed            : %.1fs", self.elapsed_seconds)
        log.info("=" * 60)
        if self.errors:
            for msg in self.errors[:5]:
                log.warning("  Error: %s", msg)
            if len(self.errors) > 5:
                log.warning("  … and %d more errors", len(self.errors) - 5)


class QdrantIngestionPipeline:
    """End-to-end pipeline: read knowledge files → embed → upsert to Qdrant.

    Flow per batch
    --------------
    1. Compute point IDs for the batch
    2. Retrieve existing content_hash values from Qdrant (skip-on-rerun)
    3. Filter out documents whose text hasn't changed
    4. Truncate texts that exceed the embedding model's context window
    5. Embed remaining texts in one API call
    6. Build PointStructs with payload
    7. Upsert to Qdrant (wait=True for persistence)
    """

    def __init__(
        self,
        config: QdrantIngestConfig,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._config = config
        self._embedder = embedder or OpenAIEmbedder(
            model=config.embedding_model,
            expected_dim=config.embedding_dim,
        )

    def _make_client(self):
        from qdrant_client import QdrantClient

        return QdrantClient(
            url=self._config.qdrant_url,
            api_key=self._config.qdrant_api_key,
        )

    def run(self) -> IngestResult:
        result = IngestResult()
        start = time.time()
        ingestion_ts = datetime.now(timezone.utc).isoformat()

        cfg = self._config
        loader = KnowledgeLoader(cfg.knowledge_dir)
        docs = list(loader.load_all())
        result.total_loaded = len(docs)

        if not docs:
            log.warning("No knowledge files found in %s. Nothing to ingest.", cfg.knowledge_dir)
            result.elapsed_seconds = time.time() - start
            return result

        if cfg.dry_run:
            log.info("[DRY RUN] Would ingest %d documents into '%s'. No writes performed.", len(docs), cfg.collection_name)
            result.elapsed_seconds = time.time() - start
            return result

        # Connect and bootstrap collection
        client = self._make_client()
        mgr = CollectionManager(client, cfg.collection_name, self._embedder.dim)
        newly_created = mgr.ensure()
        if newly_created:
            mgr.create_payload_indexes()

        upserter = QdrantUpserter(client, cfg.collection_name)

        # Filter low-quality documents
        if cfg.min_quality_score > 0.0:
            before = len(docs)
            docs = [d for d in docs if float(d.get("quality_score", 0.0)) >= cfg.min_quality_score]
            result.skipped_low_quality = before - len(docs)
            if result.skipped_low_quality:
                log.info("Skipped %d low-quality docs (score < %.2f)", result.skipped_low_quality, cfg.min_quality_score)

        # Process in batches
        for batch_start in range(0, len(docs), cfg.batch_size):
            batch = docs[batch_start: batch_start + cfg.batch_size]
            batch_num = batch_start // cfg.batch_size + 1
            total_batches = (len(docs) + cfg.batch_size - 1) // cfg.batch_size

            if batch_start % (cfg.log_every * cfg.batch_size // cfg.batch_size or 1) == 0:
                log.info(
                    "Batch %d/%d — processed so far: embedded=%d upserted=%d skipped=%d failed=%d",
                    batch_num,
                    total_batches,
                    result.embedded,
                    result.upserted,
                    result.skipped_unchanged,
                    result.failed,
                )

            try:
                upserted = self._process_batch(batch, upserter, result, ingestion_ts, cfg)
                result.upserted += upserted
            except Exception as exc:
                msg = f"Batch {batch_num} failed: {exc}"
                log.error(msg)
                result.errors.append(msg)
                result.failed += len(batch)

        result.elapsed_seconds = time.time() - start
        result.print_summary()
        return result

    def _process_batch(
        self,
        batch: list[dict],
        upserter: QdrantUpserter,
        result: IngestResult,
        ingestion_ts: str,
        cfg: QdrantIngestConfig,
    ) -> int:
        from qdrant_client.models import PointStruct

        point_ids = [doc_to_point_id(d["document_id"]) for d in batch]

        # Skip unchanged documents unless overwrite is requested
        to_embed_docs = batch
        if not cfg.overwrite:
            existing_hashes = upserter.check_existing(point_ids)
            to_embed_docs = []
            for doc, pid in zip(batch, point_ids):
                text = doc_to_text(doc)
                if existing_hashes.get(pid) == content_hash(text):
                    result.skipped_unchanged += 1
                else:
                    to_embed_docs.append(doc)

        if not to_embed_docs:
            return 0  # entire batch unchanged

        # Collect texts — truncation to model token limit is handled by the embedder
        texts = [doc_to_text(doc) for doc in to_embed_docs]

        # Embed
        vectors = self._embedder.embed_batch(texts)
        result.embedded += len(vectors)

        # Build points
        points = []
        for doc, vector in zip(to_embed_docs, vectors):
            pid = doc_to_point_id(doc["document_id"])
            payload = doc_to_payload(doc, ingestion_ts)
            points.append(PointStruct(id=pid, vector=vector, payload=payload))

        # Upsert
        return upserter.upsert_batch(points)
