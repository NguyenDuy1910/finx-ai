from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.ingest.payload import chunk_to_embedding_texts, chunk_to_payload, chunk_to_point_id
from pipeline.schemas.chunk import ChunkDocument

log = logging.getLogger("finx-data.ingest.chunk_ingest")


@dataclass
class ChunkIngestConfig:
    """Configuration for chunk-level Qdrant ingestion."""

    chunks_dir: str | Path = "output/chunks"

    # Qdrant connection
    qdrant_url: str = field(default_factory=lambda: os.environ.get("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str | None = field(default_factory=lambda: os.environ.get("QDRANT_API_KEY"))

    # Collection
    collection_name: str = "finx_chunks"
    embedding_model: str = field(default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"))
    embedding_dim: int = 1536

    # Behaviour
    batch_size: int = 100
    dry_run: bool = False
    overwrite: bool = False


@dataclass
class ChunkIngestResult:
    """Summary of a chunk ingestion run."""

    total_loaded: int = 0
    skipped_unchanged: int = 0
    embedded: int = 0
    upserted: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def print_summary(self) -> None:
        log.info("=" * 60)
        log.info("Chunk ingestion summary")
        log.info("  Total loaded       : %d", self.total_loaded)
        log.info("  Skipped (unchanged): %d", self.skipped_unchanged)
        log.info("  Embedded           : %d", self.embedded)
        log.info("  Upserted           : %d", self.upserted)
        log.info("  Failed             : %d", self.failed)
        log.info("  Elapsed            : %.1fs", self.elapsed_seconds)
        log.info("=" * 60)


class ChunkIngestionPipeline:
    """Load ChunkDocument JSON → embed → upsert to Qdrant."""

    def __init__(self, config: ChunkIngestConfig) -> None:
        self._config = config

    def _load_chunks(self) -> list[ChunkDocument]:
        """Recursively load ChunkDocument JSON files from chunks_dir."""
        chunks_dir = Path(self._config.chunks_dir)
        if not chunks_dir.exists():
            log.warning("Chunks directory does not exist: %s", chunks_dir)
            return []

        chunks: list[ChunkDocument] = []
        for path in sorted(chunks_dir.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                chunk = ChunkDocument(**data)
                chunks.append(chunk)
            except Exception as exc:
                log.warning("Failed to load chunk %s: %s", path.name, exc)
        return chunks

    def _make_client(self):
        from qdrant_client import QdrantClient
        return QdrantClient(
            url=self._config.qdrant_url,
            api_key=self._config.qdrant_api_key,
        )

    def _ensure_collection(self, client) -> None:
        """Create collection if it doesn't exist and set up payload indexes."""
        from qdrant_client.models import Distance, VectorParams

        collections = [c.name for c in client.get_collections().collections]
        if self._config.collection_name not in collections:
            client.create_collection(
                collection_name=self._config.collection_name,
                vectors_config=VectorParams(
                    size=self._config.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            log.info("Created collection '%s'", self._config.collection_name)
            self._create_payload_indexes(client)

    def _create_payload_indexes(self, client) -> None:
        """Create payload indexes for filtered retrieval."""
        from qdrant_client.models import PayloadSchemaType

        keyword_fields = [
            "doc_id", "source_system", "doc_type", "language",
            "space_key", "project_key", "chunk_kind", "is_public",
            "source_type", "content_type", "ticket_status", "ticket_type",
            "attachment_id", "comment_id", "parent_content_id", "mime_type",
        ]
        for field_name in keyword_fields:
            client.create_payload_index(
                collection_name=self._config.collection_name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )

        # Array keyword fields
        for field_name in ["domains", "acl_readers", "acl_spaces", "section_path", "keywords"]:
            client.create_payload_index(
                collection_name=self._config.collection_name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )

        # Float index for quality filtering
        client.create_payload_index(
            collection_name=self._config.collection_name,
            field_name="quality_score",
            field_schema=PayloadSchemaType.FLOAT,
        )

        log.info("Created payload indexes for collection '%s'", self._config.collection_name)

    def run(self) -> ChunkIngestResult:
        result = ChunkIngestResult()
        start = time.time()

        chunks = self._load_chunks()
        result.total_loaded = len(chunks)

        if not chunks:
            log.warning("No chunk files found in %s", self._config.chunks_dir)
            result.elapsed_seconds = time.time() - start
            return result

        if self._config.dry_run:
            log.info("[DRY RUN] Would ingest %d chunks into '%s'",
                     len(chunks), self._config.collection_name)
            result.elapsed_seconds = time.time() - start
            return result

        client = self._make_client()
        self._ensure_collection(client)

        from pipeline.ingest.embedder import OpenAIEmbedder
        from pipeline.ingest.upserter import QdrantUpserter

        embedder = OpenAIEmbedder(
            model=self._config.embedding_model,
            expected_dim=self._config.embedding_dim,
        )
        upserter = QdrantUpserter(client, self._config.collection_name)

        # Process in batches
        for batch_start in range(0, len(chunks), self._config.batch_size):
            batch = chunks[batch_start:batch_start + self._config.batch_size]
            try:
                upserted = self._process_batch(batch, embedder, upserter, result)
                result.upserted += upserted
            except Exception as exc:
                msg = f"Batch failed: {exc}"
                log.error(msg)
                result.errors.append(msg)
                result.failed += len(batch)

        result.elapsed_seconds = time.time() - start
        result.print_summary()
        return result

    def _process_batch(
        self,
        batch: list[ChunkDocument],
        embedder,
        upserter,
        result: ChunkIngestResult,
    ) -> int:
        from qdrant_client.models import PointStruct

        # Skip unchanged chunks
        to_embed = batch
        if not self._config.overwrite:
            point_ids = [chunk_to_point_id(c.chunk_id) for c in batch]
            existing_hashes = upserter.check_existing(point_ids)
            to_embed = []
            for chunk, pid in zip(batch, point_ids):
                if existing_hashes.get(pid) == chunk.chunk_hash:
                    result.skipped_unchanged += 1
                else:
                    to_embed.append(chunk)

        if not to_embed:
            return 0

        # Build embedding texts (use dense text only for now)
        texts = [chunk_to_embedding_texts(c)[0] for c in to_embed]

        # Embed
        vectors = embedder.embed_batch(texts)
        result.embedded += len(vectors)

        # Build points
        points = []
        for chunk, vector in zip(to_embed, vectors):
            pid = chunk_to_point_id(chunk.chunk_id)
            payload = chunk_to_payload(chunk)
            points.append(PointStruct(id=pid, vector=vector, payload=payload))

        return upserter.upsert_batch(points)
