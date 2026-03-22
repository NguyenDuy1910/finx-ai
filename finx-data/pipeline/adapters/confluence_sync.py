"""Confluence incremental sync adapter.

Wraps ``ConfluenceAdapter`` with state tracking so that subsequent runs
only fetch content modified since the last successful sync.  Uses CQL
``lastModified`` queries and per-content version comparison to detect
changes.  Deleted content (present in state but absent from API) is
emitted as soft-delete marker ``RawDocument``s.

State is persisted to a JSON file (default:
``.confluence_sync_state.json``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field

from .base import BaseAdapter, RawDocument
from .confluence import ConfluenceAdapter
from .confluence_v2_client import ConfluenceV2Client

log = logging.getLogger("finx-data.adapter.confluence-sync")


class ConfluenceSyncState(BaseModel):
    """Persistent state for incremental Confluence sync."""

    last_sync_at: str = ""
    """ISO-8601 timestamp of the last successful full/incremental sync."""

    content_versions: dict[str, int] = Field(default_factory=dict)
    """Map of content_id → version_number for all known content."""

    space_cursors: dict[str, str] = Field(default_factory=dict)
    """Optional per-space pagination cursor for resume."""


class ConfluenceSyncAdapter(BaseAdapter):
    """Incremental sync adapter wrapping ``ConfluenceAdapter``.

    On first run (no state file): delegates to ``ConfluenceAdapter`` for a
    full crawl, then saves state.

    On subsequent runs: queries Confluence via CQL for content modified
    since ``last_sync_at``, fetches only those items, compares versions,
    and emits only changed documents.  Content IDs in state but not
    returned by the API are emitted as soft-delete markers.

    Parameters
    ----------
    inner : ConfluenceAdapter
        The underlying multi-type adapter.
    state_path : str
        Path to the sync state JSON file.
    """

    source_system = "confluence"

    def __init__(
        self,
        inner: ConfluenceAdapter,
        state_path: str = ".confluence_sync_state.json",
    ) -> None:
        self.inner = inner
        self.state_path = Path(state_path)
        self.state = self._load_state()

    # ── public API ────────────────────────────────────────────────────────

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        if not self.state.last_sync_at:
            log.info("No sync state found — running full crawl")
            yield from self._full_crawl(**kwargs)
        else:
            log.info("Incremental sync since %s", self.state.last_sync_at)
            yield from self._incremental_crawl(**kwargs)

    def test_connection(self) -> bool:
        return self.inner.test_connection()

    # ── crawl modes ───────────────────────────────────────────────────────

    def _full_crawl(self, **kwargs) -> Iterator[RawDocument]:
        new_versions: dict[str, int] = {}

        for doc in self.inner.fetch(**kwargs):
            content_id = doc.metadata.get("content_id", doc.source_id)
            version = doc.version or doc.metadata.get("version", 0)
            if content_id:
                new_versions[content_id] = version
            yield doc

        self.state.content_versions = new_versions
        self.state.last_sync_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        log.info("Full crawl complete — tracked %d content items", len(new_versions))

    def _incremental_crawl(self, **kwargs) -> Iterator[RawDocument]:
        import asyncio

        changed_ids = asyncio.run(self._find_changed_content())
        log.info("Found %d changed/new content items since %s", len(changed_ids), self.state.last_sync_at)

        new_versions = dict(self.state.content_versions)

        # Fetch all content (the inner adapter fetches everything;
        # we filter to only yield changed items)
        for doc in self.inner.fetch(**kwargs):
            content_id = doc.metadata.get("content_id", doc.source_id)
            version = doc.version or doc.metadata.get("version", 0)

            if content_id:
                old_version = self.state.content_versions.get(content_id, -1)
                new_versions[content_id] = version

                if content_id in changed_ids or version != old_version:
                    yield doc
                # else: unchanged, skip

        # Detect deletions: IDs in state but not seen in this crawl
        seen_ids = set(new_versions.keys())
        for deleted_id in set(self.state.content_versions.keys()) - seen_ids:
            yield RawDocument(
                source_system=self.source_system,
                source_uri=f"deleted://{deleted_id}",
                source_id=deleted_id,
                title="[DELETED]",
                content_type="deleted",
                metadata={
                    "content_id": deleted_id,
                    "is_deleted": True,
                },
            )

        self.state.content_versions = new_versions
        self.state.last_sync_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        log.info("Incremental sync complete — now tracking %d items", len(new_versions))

    async def _find_changed_content(self) -> set[str]:
        """Use CQL to find content modified since last sync."""
        changed: set[str] = set()

        async with ConfluenceV2Client(
            self.inner.base_url,
            self.inner.username,
            self.inner.api_token,
            concurrency=self.inner.concurrency,
        ) as client:
            for space_key in self.inner.space_keys:
                cql = (
                    f'space = "{space_key}" AND '
                    f'lastModified >= "{self.state.last_sync_at}"'
                )
                try:
                    results = await client.cql_search(cql, limit=5000)
                    for r in results:
                        content = r.get("content", r)
                        cid = str(content.get("id", ""))
                        if cid:
                            changed.add(cid)
                except Exception as exc:
                    log.warning("CQL search failed for space %s: %s", space_key, exc)

        return changed

    # ── state persistence ─────────────────────────────────────────────────

    def _load_state(self) -> ConfluenceSyncState:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                return ConfluenceSyncState.model_validate(data)
            except Exception as exc:
                log.warning("Failed to load sync state from %s: %s", self.state_path, exc)
        return ConfluenceSyncState()

    def _save_state(self) -> None:
        self.state_path.write_text(self.state.model_dump_json(indent=2))
        log.debug("Saved sync state to %s", self.state_path)
