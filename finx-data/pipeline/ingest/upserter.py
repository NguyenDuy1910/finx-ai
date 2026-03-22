"""Qdrant batch upsert with retry and existing-point lookup."""

from __future__ import annotations

import logging
import time

log = logging.getLogger("finx-data.ingest.upserter")

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class QdrantUpserter:
    """Handles batch upserts and existing-point checks against Qdrant."""

    def __init__(self, client, collection_name: str) -> None:
        self._client = client
        self._name = collection_name

    def check_existing(self, point_ids: list[str]) -> dict[str, str]:
        """Retrieve the chunk_hash of already-indexed points.

        Returns a mapping of {point_id: chunk_hash} for points that exist.
        Unknown IDs are simply absent from the result dict.
        """
        if not point_ids:
            return {}

        try:
            records = self._client.retrieve(
                collection_name=self._name,
                ids=point_ids,
                with_payload=["chunk_hash"],
                with_vectors=False,
            )
            return {
                str(r.id): r.payload.get("chunk_hash", "")
                for r in records
                if r.payload
            }
        except Exception as exc:
            # Non-fatal: on failure we treat all as new (safe — just re-embeds them)
            log.warning("Could not retrieve existing point hashes (%s). Treating all as new.", exc)
            return {}

    def upsert_batch(self, points: list) -> int:
        """Upsert a list of PointStruct objects with retry.

        Returns the number of points successfully upserted.
        Raises on persistent failure after max retries.
        """
        if not points:
            return 0

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._client.upsert(
                    collection_name=self._name,
                    points=points,
                    wait=True,   # ensure persistence before proceeding
                )
                return len(points)

            except Exception as exc:
                if attempt == _MAX_RETRIES:
                    log.error(
                        "Upsert failed after %d attempts: %s. %d points lost.",
                        _MAX_RETRIES,
                        exc,
                        len(points),
                    )
                    raise

                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log.warning(
                    "Upsert attempt %d/%d failed (%s). Retrying in %.1fs…",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)

        return 0  # unreachable
