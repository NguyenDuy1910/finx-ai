"""Athena / Glue schema metadata adapter.

Wraps the existing ``readers.read_athena_schemas`` to produce
``RawDocument`` instances for the pipeline.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterator

from .base import BaseAdapter, RawDocument

log = logging.getLogger("finx-data.adapter.athena")


class AthenaSchemaAdapter(BaseAdapter):
    """Fetch table schema metadata from AWS Athena / Glue."""

    source_system = "athena"

    def __init__(
        self,
        database: str | None = None,
        concurrency: int | None = None,
    ):
        self.database = database or os.environ.get("ATHENA_DATABASE", "")
        self.concurrency = concurrency

    def test_connection(self) -> bool:
        try:
            import boto3

            region = os.getenv("AWS_REGION", "ap-southeast-1")
            client = boto3.client("athena", region_name=region)
            client.list_work_groups(MaxResults=1)
            return True
        except Exception as exc:
            log.warning("Athena connection test failed: %s", exc)
            return False

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        """Yield one RawDocument per table in the configured database."""
        from readers import read_athena_schemas

        database = kwargs.get("database", self.database)
        concurrency = kwargs.get("concurrency", self.concurrency)

        schemas = read_athena_schemas(
            database=database,
            concurrency=concurrency,
        )

        for schema in schemas:
            table_name = schema.get("name", "unknown")
            db = schema.get("database", database)

            yield RawDocument(
                source_system=self.source_system,
                source_uri=f"athena://{db}/{table_name}",
                source_id=f"{db}.{table_name}",
                title=table_name,
                raw_content=schema.get("content", ""),
                metadata={
                    "database": db,
                    "table_name": table_name,
                    "table_comment": schema.get("table_comment", ""),
                    "storage_format": schema.get("storage_format", ""),
                    "s3_location": schema.get("s3_location", ""),
                    "owner": schema.get("owner", ""),
                    "table_type": schema.get("table_type", ""),
                    "row_count": schema.get("row_count"),
                    "columns": schema.get("columns", []),
                    "partition_keys": schema.get("partition_keys", []),
                },
                mime_type="application/x-schema",
            )
