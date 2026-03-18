"""Confluence source adapter.

Wraps the existing ``readers.read_confluence_page_list`` and
``readers.read_confluence_page`` functions, producing ``RawDocument``
instances for the pipeline.

Uses concurrent fetching (ThreadPoolExecutor) to speed up page body
retrieval when processing many pages across Confluence spaces.
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterator

from .base import BaseAdapter, RawDocument

log = logging.getLogger("finx-data.adapter.confluence")

# Default concurrent page-body fetches.
_DEFAULT_CONCURRENCY = 8


class ConfluenceAdapter(BaseAdapter):
    """Fetch pages from one or more Confluence spaces."""

    source_system = "confluence"

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
        space_keys: list[str] | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
    ):
        self.base_url = base_url or os.environ.get("CONFLUENCE_URL", "")
        self.username = username or os.environ.get("CONFLUENCE_USERNAME", "")
        self.api_token = api_token or os.environ.get("CONFLUENCE_API_TOKEN", "")
        self.space_keys = space_keys or [
            s.strip()
            for s in os.environ.get("CONFLUENCE_SPACE_KEYS", "DATA").split(",")
            if s.strip()
        ]
        self.concurrency = max(1, concurrency)

    def test_connection(self) -> bool:
        try:
            from atlassian import Confluence

            client = Confluence(
                url=self.base_url,
                username=self.username,
                password=self.api_token,
                cloud=True,
            )
            client.get_all_spaces(limit=1)
            return True
        except Exception as exc:
            log.warning("Confluence connection test failed: %s", exc)
            return False

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        """Yield one RawDocument per Confluence page across configured spaces.

        Uses ThreadPoolExecutor to fetch page bodies concurrently. This
        dramatically speeds up pipelines with hundreds of pages.

        Keyword args
        ------------
        page_url : str | None
            If set, fetch exactly one page by URL instead of listing spaces.
        limit : int
            Max pages per space (default 2000).
        concurrency : int
            Override instance-level concurrency for this run.
        """
        page_url: str | None = kwargs.get("page_url")
        if page_url:
            yield from self._fetch_single(page_url)
            return

        limit = kwargs.get("limit", 2000)
        concurrency = kwargs.get("concurrency", self.concurrency)
        from readers import read_confluence_page_list

        page_metas = read_confluence_page_list(
            space_keys=self.space_keys,
            base_url=self.base_url,
            username=self.username,
            api_token=self.api_token,
            limit=limit,
        )

        log.info("Fetching %d page bodies (concurrency=%d) ...", len(page_metas), concurrency)

        # Concurrent page-body fetching
        from readers import read_confluence_page

        def _fetch_body(meta: dict) -> tuple[dict, dict | None]:
            """Fetch a single page body — runs inside the thread pool."""
            url = meta.get("url", "")
            try:
                return meta, read_confluence_page(page_url=url)
            except Exception as exc:
                log.warning("Failed to fetch %s: %s", url, exc)
                return meta, None

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(_fetch_body, m): m for m in page_metas}
            for future in as_completed(futures):
                meta, page_data = future.result()
                if not page_data:
                    log.warning("Empty content for page %s (%s)", meta.get("page_id"), meta.get("title"))
                    continue

                yield RawDocument(
                    source_system=self.source_system,
                    source_uri=meta.get("url", ""),
                    source_id=meta.get("page_id", ""),
                    title=meta.get("title", ""),
                    raw_content=page_data.get("content", ""),
                    raw_html=page_data.get("raw_html", ""),
                    metadata={
                        "space_key": meta.get("space", ""),
                        "page_id": meta.get("page_id", ""),
                        "confluence_url": meta.get("url", ""),
                    },
                )

    def _fetch_single(self, page_url: str) -> Iterator[RawDocument]:
        """Fetch a single Confluence page by URL."""
        from readers import read_confluence_page

        page_data = read_confluence_page(page_url=page_url)
        if not page_data:
            return

        yield RawDocument(
            source_system=self.source_system,
            source_uri=page_data.get("url", page_url),
            source_id=page_data.get("page_id", ""),
            title=page_data.get("title", ""),
            raw_content=page_data.get("content", ""),
            raw_html=page_data.get("raw_html", ""),
            metadata={
                "space_key": page_data.get("space", ""),
                "page_id": page_data.get("page_id", ""),
            },
        )
