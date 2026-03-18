"""Qdrant ingestion stage for the finx-data pipeline.

Reads processed knowledge files from output/knowledge/ and upserts them
into a Qdrant collection as dense vector embeddings.
"""

from .config import QdrantIngestConfig
from .pipeline import IngestResult, QdrantIngestionPipeline

__all__ = ["QdrantIngestConfig", "QdrantIngestionPipeline", "IngestResult"]
