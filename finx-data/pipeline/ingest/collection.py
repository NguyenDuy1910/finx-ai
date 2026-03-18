"""Qdrant collection bootstrap — create or validate the target collection."""

from __future__ import annotations

import logging

log = logging.getLogger("finx-data.ingest.collection")


class CollectionManager:
    """Ensures the Qdrant collection exists with the correct configuration.

    Design choices:
    - Distance.COSINE: standard for normalized text embeddings.
    - Single dense vector named 'default' (no named-vector complexity).
    - Payload indexes only on fields used for filtering.
    """

    def __init__(self, client, collection_name: str, dim: int) -> None:
        self._client = client
        self._name = collection_name
        self._dim = dim

    def ensure(self) -> bool:
        """Create collection if missing; validate dim if it already exists.

        Returns True if the collection was newly created, False if it existed.
        Raises ValueError if the existing collection has a different vector size.
        """
        from qdrant_client.models import Distance, VectorParams

        exists = self._client.collection_exists(self._name)

        if not exists:
            log.info("Creating Qdrant collection '%s' (dim=%d, COSINE)", self._name, self._dim)
            self._client.create_collection(
                collection_name=self._name,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )
            log.info("Collection '%s' created.", self._name)
            return True

        # Validate existing collection
        info = self._client.get_collection(self._name)
        existing_dim = info.config.params.vectors.size
        if existing_dim != self._dim:
            raise ValueError(
                f"Collection '{self._name}' already exists with dim={existing_dim}, "
                f"but the configured embedding_dim={self._dim}. "
                "Either update embedding_dim in config or delete/recreate the collection."
            )

        log.info(
            "Collection '%s' already exists (dim=%d). Using existing collection.",
            self._name,
            existing_dim,
        )
        return False

    def create_payload_indexes(self) -> None:
        """Create payload indexes on fields likely used for filtered retrieval.

        Only called when a collection is freshly created, though calling on an
        existing collection is safe (Qdrant ignores duplicate index creation).
        """
        from qdrant_client.models import PayloadSchemaType

        keyword_fields = [
            "source_system",
            "document_type",
            "language",
            "space_key",
            "domains",        # array of strings — Qdrant handles as keyword array
        ]
        float_fields = ["quality_score"]
        keyword_date_fields = ["processed_at", "ingestion_timestamp"]

        for field in keyword_fields:
            self._client.create_payload_index(
                collection_name=self._name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
            log.debug("Payload index: %s (keyword)", field)

        for field in float_fields:
            self._client.create_payload_index(
                collection_name=self._name,
                field_name=field,
                field_schema=PayloadSchemaType.FLOAT,
            )
            log.debug("Payload index: %s (float)", field)

        for field in keyword_date_fields:
            self._client.create_payload_index(
                collection_name=self._name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
            log.debug("Payload index: %s (keyword/date)", field)

        log.info("Payload indexes created for collection '%s'.", self._name)
