"""Configuration for the Qdrant chunk-level ingestion stage."""

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

    # Qdrant connection
    qdrant_url: str = field(default_factory=lambda: os.environ.get("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str | None = field(default_factory=lambda: os.environ.get("QDRANT_API_KEY"))

    # Collection names
    collection_name: str = "finx_chunks"

    # Embedding
    embedding_model: str = field(default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"))
    embedding_dim: int = 1536

    # Chunking parameters
    max_chunk_tokens: int = 400
    chunk_overlap_tokens: int = 50
    min_chunk_words: int = 10

    # Tenant/ACL
    default_tenant_id: str = field(default_factory=lambda: os.environ.get("TENANT_ID", "default"))
    default_is_public: bool = False

    # Ingestion behaviour
    batch_size: int = 100
    dry_run: bool = False
    overwrite: bool = False
    min_quality_score: float = 0.0

    # Logging
    log_every: int = 25
