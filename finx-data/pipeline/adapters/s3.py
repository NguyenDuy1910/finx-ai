"""S3 document adapter.

Fetches documents (PDF, JSON, markdown, etc.) from S3 prefixes.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterator

from .base import BaseAdapter, RawDocument

log = logging.getLogger("finx-data.adapter.s3")

_MIME_MAP = {
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".html": "text/html",
    ".htm": "text/html",
}


class S3Adapter(BaseAdapter):
    """Fetch objects from an S3 bucket/prefix."""

    source_system = "s3"

    def __init__(
        self,
        bucket: str | None = None,
        prefix: str = "",
        region: str | None = None,
    ):
        self.bucket = bucket or os.environ.get("S3_BUCKET", "")
        self.prefix = prefix or os.environ.get("S3_PREFIX", "")
        self.region = region or os.environ.get("AWS_REGION", "ap-southeast-1")

    def test_connection(self) -> bool:
        try:
            import boto3

            s3 = boto3.client("s3", region_name=self.region)
            s3.head_bucket(Bucket=self.bucket)
            return True
        except Exception as exc:
            log.warning("S3 connection test failed: %s", exc)
            return False

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        """Yield one RawDocument per S3 object under the configured prefix.

        Keyword args
        ------------
        suffixes : list[str]
            Only yield objects whose key ends with one of these (default: common doc types).
        max_objects : int
            Cap on total objects to fetch (default: no limit).
        """
        import boto3

        suffixes = kwargs.get("suffixes", list(_MIME_MAP.keys()))
        max_objects = kwargs.get("max_objects", 0)

        s3 = boto3.client("s3", region_name=self.region)
        paginator = s3.get_paginator("list_objects_v2")

        count = 0
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                key: str = obj["Key"]
                if not any(key.lower().endswith(s) for s in suffixes):
                    continue

                try:
                    resp = s3.get_object(Bucket=self.bucket, Key=key)
                    body = resp["Body"].read()
                except Exception as exc:
                    log.warning("Failed to fetch s3://%s/%s: %s", self.bucket, key, exc)
                    continue

                suffix = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""
                mime = _MIME_MAP.get(suffix, "application/octet-stream")
                is_text = mime.startswith("text/") or mime == "application/json"

                yield RawDocument(
                    source_system=self.source_system,
                    source_uri=f"s3://{self.bucket}/{key}",
                    source_id=key,
                    title=key.rsplit("/", 1)[-1],
                    raw_content=body.decode("utf-8", errors="replace") if is_text else "",
                    binary_content=body if not is_text else None,
                    metadata={
                        "bucket": self.bucket,
                        "key": key,
                        "size_bytes": obj.get("Size", 0),
                        "last_modified": obj.get("LastModified", ""),
                    },
                    mime_type=mime,
                )

                count += 1
                if max_objects and count >= max_objects:
                    return
