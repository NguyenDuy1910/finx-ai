"""Qdrant ingestion stage for the finx-data pipeline.

Chunk-level ingestion: reads ChunkDocument JSON and upserts into Qdrant.
"""

from .chunk_ingest import ChunkIngestConfig, ChunkIngestionPipeline

__all__ = ["ChunkIngestConfig", "ChunkIngestionPipeline"]
