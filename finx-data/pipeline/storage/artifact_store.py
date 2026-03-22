"""Artifact store for binary files (attachments, downloaded documents).

Provides pluggable storage backends (local filesystem or S3-compatible)
for raw binaries, keeping them out of memory during processing.
Downstream extractors load binaries on demand via ``artifact_uri``.

Backend selection is driven by the ``ARTIFACT_STORE_TYPE`` env var:

* ``local`` (default) — writes to ``output/artifacts/``
* ``s3`` — writes to an S3 / MinIO bucket
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

log = logging.getLogger("finx-data.storage")


class ArtifactStore(ABC):
    """Abstract binary artifact store."""

    @abstractmethod
    def save(self, content_id: str, filename: str, data: bytes) -> str:
        """Persist binary data and return an ``artifact_uri`` for later retrieval.

        Args:
            content_id: Source-system ID of the parent content object.
            filename: Original filename (used for path construction).
            data: Raw bytes to store.

        Returns:
            A URI string that ``load()`` can resolve.
        """
        ...

    @abstractmethod
    def load(self, artifact_uri: str) -> bytes:
        """Load binary data by its ``artifact_uri``."""
        ...

    @abstractmethod
    def exists(self, artifact_uri: str) -> bool:
        """Check whether an artifact has already been stored."""
        ...


class LocalArtifactStore(ArtifactStore):
    """Store artifacts on the local filesystem.

    Layout::

        {base_dir}/{content_id}/{filename}

    The ``artifact_uri`` is the relative path from *base_dir*.
    """

    def __init__(self, base_dir: str = "output/artifacts") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, content_id: str, filename: str, data: bytes) -> str:
        safe_id = _sanitize(content_id)
        safe_name = _sanitize(filename)
        rel = f"{safe_id}/{safe_name}"
        dest = self.base_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        log.debug("Saved artifact %s (%d bytes)", rel, len(data))
        return rel

    def load(self, artifact_uri: str) -> bytes:
        path = self.base_dir / artifact_uri
        if not path.is_file():
            raise FileNotFoundError(f"Artifact not found: {path}")
        return path.read_bytes()

    def exists(self, artifact_uri: str) -> bool:
        return (self.base_dir / artifact_uri).is_file()


class S3ArtifactStore(ArtifactStore):
    """Store artifacts in an S3-compatible bucket (AWS S3, MinIO, etc.).

    Layout inside the bucket::

        {prefix}/{content_id}/{filename}

    The ``artifact_uri`` returned is ``s3://{bucket}/{key}``.

    Env vars
    --------
    S3_ARTIFACT_BUCKET       Bucket name (required)
    S3_ARTIFACT_PREFIX       Key prefix inside the bucket (default: ``artifacts``)
    S3_ENDPOINT_URL          Custom endpoint for MinIO / LocalStack (optional)
    AWS_REGION               AWS region (default: ``ap-southeast-1``)
    AWS_ACCESS_KEY_ID        Credentials (or use IAM role / profile)
    AWS_SECRET_ACCESS_KEY
    """

    def __init__(
        self,
        bucket: str | None = None,
        prefix: str | None = None,
        endpoint_url: str | None = None,
        region: str | None = None,
    ) -> None:
        import boto3

        self.bucket = bucket or os.environ.get("S3_ARTIFACT_BUCKET", "")
        if not self.bucket:
            raise ValueError(
                "S3ArtifactStore requires a bucket name. "
                "Set S3_ARTIFACT_BUCKET env var or pass bucket= parameter."
            )
        self.prefix = (prefix or os.environ.get("S3_ARTIFACT_PREFIX", "artifacts")).strip("/")
        self._endpoint_url = endpoint_url or os.environ.get("S3_ENDPOINT_URL") or None
        self._region = region or os.environ.get("AWS_REGION", "ap-southeast-1")

        session_kwargs: dict = {"region_name": self._region}
        client_kwargs: dict = {}
        if self._endpoint_url:
            client_kwargs["endpoint_url"] = self._endpoint_url
        self._s3 = boto3.client("s3", **session_kwargs, **client_kwargs)
        log.info("S3ArtifactStore: bucket=%s prefix=%s endpoint=%s", self.bucket, self.prefix, self._endpoint_url or "default")

    def _key(self, content_id: str, filename: str) -> str:
        safe_id = _sanitize(content_id)
        safe_name = _sanitize(filename)
        return f"{self.prefix}/{safe_id}/{safe_name}" if self.prefix else f"{safe_id}/{safe_name}"

    def _key_from_uri(self, artifact_uri: str) -> str:
        """Extract the S3 key from an artifact URI."""
        if artifact_uri.startswith("s3://"):
            # s3://bucket/key → key
            without_scheme = artifact_uri[5:]
            return without_scheme.split("/", 1)[1] if "/" in without_scheme else ""
        return artifact_uri

    def save(self, content_id: str, filename: str, data: bytes) -> str:
        key = self._key(content_id, filename)
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data)
        uri = f"s3://{self.bucket}/{key}"
        log.debug("Saved artifact %s (%d bytes)", uri, len(data))
        return uri

    def load(self, artifact_uri: str) -> bytes:
        key = self._key_from_uri(artifact_uri)
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except self._s3.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Artifact not found in S3: {artifact_uri}")

    def exists(self, artifact_uri: str) -> bool:
        key = self._key_from_uri(artifact_uri)
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False


# ── Factory ───────────────────────────────────────────────────────────────────


def create_artifact_store(**kwargs) -> ArtifactStore:
    """Create an artifact store based on ``ARTIFACT_STORE_TYPE`` env var.

    * ``local`` (default) → :class:`LocalArtifactStore`
    * ``s3`` → :class:`S3ArtifactStore`
    """
    store_type = os.environ.get("ARTIFACT_STORE_TYPE", "local").lower()

    if store_type == "s3":
        return S3ArtifactStore(**kwargs)

    return LocalArtifactStore(**kwargs)


def _sanitize(name: str) -> str:
    """Replace path-unsafe characters with underscores."""
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in name)
