"""Configuration for the Qdrant ingestion stage."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class QdrantIngestConfig:
    """All settings for one ingestion run.

    Environment variables are read at instantiation time as fallbacks.
    CLI args take priority over env vars.
    """

    # Input
    knowledge_dir: str | Path = "output/knowledge"

    # Qdrant connection
    qdrant_url: str = field(default_factory=lambda: os.environ.get("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str | None = field(default_factory=lambda: os.environ.get("QDRANT_API_KEY"))
    collection_name: str = field(default_factory=lambda: os.environ.get("QDRANT_COLLECTION", "finx_knowledge"))

    # Embedding
    embedding_model: str = field(default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"))
    embedding_dim: int = 1536  # text-embedding-3-small default; update if model changes

    # Ingestion behaviour
    batch_size: int = 100       # points per upsert call
    dry_run: bool = False       # log actions but do not write to Qdrant
    overwrite: bool = False     # re-embed even when content hash matches existing point
    min_quality_score: float = 0.0  # skip documents below this score (0.0 = no filter)

    # Logging
    log_every: int = 25         # log progress every N documents
