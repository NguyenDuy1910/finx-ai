"""Jira incremental sync adapter.

Same pattern as ``ConfluenceSyncAdapter`` — wraps ``JiraAdapter`` with
state tracking so subsequent runs only fetch issues updated since the
last successful sync.  Uses JQL ``updated >= "date"`` for incremental
discovery and per-issue update timestamps for change detection.

State is persisted to a JSON file (default:
``.jira_sync_state.json``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field

from .base import BaseAdapter, RawDocument
from .jira import JiraAdapter
from .jira_client import JiraV2Client

log = logging.getLogger("finx-data.adapter.jira-sync")


class JiraSyncState(BaseModel):
    """Persistent state for incremental Jira sync."""

    last_sync_at: str = ""
    """ISO-8601 timestamp of the last successful sync."""

    issue_versions: dict[str, str] = Field(default_factory=dict)
    """Map of issue_key → last-seen updated timestamp (ISO-8601)."""


class JiraSyncAdapter(BaseAdapter):
    """Incremental sync adapter wrapping ``JiraAdapter``.

    On first run (no state file): delegates to ``JiraAdapter`` for a
    full crawl, then saves state.

    On subsequent runs: queries Jira via JQL for issues updated since
    ``last_sync_at``, fetches those items, compares update timestamps,
    and emits only changed documents.  Issue keys in state but not
    returned by the API are emitted as soft-delete markers.

    Parameters
    ----------
    inner : JiraAdapter
        The underlying multi-type adapter.
    state_path : str
        Path to the sync state JSON file.
    """

    source_system = "jira"

    def __init__(
        self,
        inner: JiraAdapter,
        state_path: str = ".jira_sync_state.json",
    ) -> None:
        self.inner = inner
        self.state_path = Path(state_path)
        self.state = self._load_state()

    # ── public API ────────────────────────────────────────────────────────

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        if not self.state.last_sync_at:
            log.info("No Jira sync state found — running full crawl")
            yield from self._full_crawl(**kwargs)
        else:
            log.info("Jira incremental sync since %s", self.state.last_sync_at)
            yield from self._incremental_crawl(**kwargs)

    def test_connection(self) -> bool:
        return self.inner.test_connection()

    # ── crawl modes ───────────────────────────────────────────────────────

    def _full_crawl(self, **kwargs) -> Iterator[RawDocument]:
        new_versions: dict[str, str] = {}

        for doc in self.inner.fetch(**kwargs):
            issue_key = doc.metadata.get("issue_key", doc.source_id)
            updated = doc.metadata.get("updated", "")

            if issue_key and doc.content_type != "deleted":
                new_versions[issue_key] = updated
            yield doc

        self.state.issue_versions = new_versions
        self.state.last_sync_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        log.info("Jira full crawl complete — tracked %d issues", len(new_versions))

    def _incremental_crawl(self, **kwargs) -> Iterator[RawDocument]:
        import asyncio

        changed_keys = asyncio.run(self._find_changed_issues())
        log.info(
            "Found %d changed/new issues since %s",
            len(changed_keys),
            self.state.last_sync_at,
        )

        new_versions = dict(self.state.issue_versions)

        for doc in self.inner.fetch(**kwargs):
            issue_key = doc.metadata.get("issue_key", doc.source_id)
            updated = doc.metadata.get("updated", "")

            if issue_key and doc.content_type != "deleted":
                old_updated = self.state.issue_versions.get(issue_key, "")
                new_versions[issue_key] = updated

                if issue_key in changed_keys or updated != old_updated:
                    yield doc
                # else: unchanged, skip

        # Detect deletions: keys in state but not seen in this crawl
        seen_keys = set(new_versions.keys())
        for deleted_key in set(self.state.issue_versions.keys()) - seen_keys:
            yield RawDocument(
                source_system=self.source_system,
                source_uri=f"deleted://{deleted_key}",
                source_id=deleted_key,
                title="[DELETED]",
                content_type="deleted",
                metadata={
                    "issue_key": deleted_key,
                    "is_deleted": True,
                },
            )

        self.state.issue_versions = new_versions
        self.state.last_sync_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        log.info(
            "Jira incremental sync complete — now tracking %d issues",
            len(new_versions),
        )

    async def _find_changed_issues(self) -> set[str]:
        """Use JQL to find issues updated since last sync."""
        changed: set[str] = set()

        # Format date for JQL: YYYY-MM-DD HH:mm
        # JQL `updated` operator uses "YYYY/MM/DD HH:mm" format
        try:
            dt = datetime.fromisoformat(self.state.last_sync_at)
            jql_date = dt.strftime("%Y/%m/%d %H:%M")
        except (ValueError, TypeError):
            log.warning("Invalid last_sync_at: %s, falling back to full scan", self.state.last_sync_at)
            return changed

        async with JiraV2Client(
            self.inner.base_url,
            self.inner.username,
            self.inner.api_token,
            concurrency=self.inner.concurrency,
        ) as client:
            for project_key in self.inner.project_keys:
                jql = (
                    f'project = "{project_key}" AND '
                    f'updated >= "{jql_date}"'
                )
                try:
                    issues = await client.search_issues(
                        jql=jql,
                        fields=["key"],
                        max_results=5000,
                    )
                    for issue in issues:
                        key = issue.get("key", "")
                        if key:
                            changed.add(key)
                except Exception as exc:
                    log.warning(
                        "JQL search failed for project %s: %s",
                        project_key,
                        exc,
                    )

        return changed

    # ── state persistence ─────────────────────────────────────────────────

    def _load_state(self) -> JiraSyncState:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                return JiraSyncState.model_validate(data)
            except Exception as exc:
                log.warning(
                    "Failed to load Jira sync state from %s: %s",
                    self.state_path,
                    exc,
                )
        return JiraSyncState()

    def _save_state(self) -> None:
        self.state_path.write_text(self.state.model_dump_json(indent=2))
        log.debug("Saved Jira sync state to %s", self.state_path)
