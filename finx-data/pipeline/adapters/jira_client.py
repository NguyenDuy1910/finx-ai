"""Jira Cloud REST API v2 client.

Async HTTP client wrapping ``/rest/api/2/`` endpoints for issue search,
details, comments, attachments, worklogs, and changelogs.

Uses ``httpx.AsyncClient`` with Basic auth, semaphore-based rate limiting,
and exponential backoff on transient errors.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any

import httpx

log = logging.getLogger("finx-data.jira-v2")

_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0


class JiraV2Client:
    """Async client for the Jira Cloud REST API v2.

    Env vars
    --------
    JIRA_URL            Base URL  (e.g. ``https://org.atlassian.net``)
    JIRA_USERNAME       Atlassian account email
    JIRA_API_TOKEN      API token from id.atlassian.com
    """

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
        concurrency: int = 8,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or os.environ.get("JIRA_URL", "")).rstrip("/")
        self._username = username or os.environ.get("JIRA_USERNAME", "")
        self._token = api_token or os.environ.get("JIRA_API_TOKEN", "")
        self._sem = asyncio.Semaphore(concurrency)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "JiraV2Client":
        cred = base64.b64encode(f"{self._username}:{self._token}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/rest/api/2",
            headers={
                "Authorization": f"Basic {cred}",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── low-level ─────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> dict:
        assert self._client is not None, "Use `async with` to open the client"
        async with self._sem:
            return await self._request_with_retry("GET", path, params=params)

    async def _request_with_retry(
        self, method: str, path: str, *, params: dict | None = None
    ) -> dict:
        assert self._client is not None
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.request(method, path, params=params)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", _BACKOFF_BASE * (2 ** attempt)))
                    log.warning("Rate-limited (429), retrying after %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    log.warning("Jira request %s %s failed (%s), retry in %.1fs", method, path, exc, wait)
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    async def _download(self, url: str) -> bytes:
        """Download binary content from an absolute URL."""
        assert self._client is not None
        cred = base64.b64encode(f"{self._username}:{self._token}".encode()).decode()
        async with self._sem:
            async with httpx.AsyncClient(
                headers={"Authorization": f"Basic {cred}"},
                timeout=self._timeout,
            ) as dl:
                resp = await dl.get(url)
                resp.raise_for_status()
                return resp.content

    # ── Search ────────────────────────────────────────────────────────────

    async def search_issues(
        self,
        jql: str,
        *,
        fields: list[str] | None = None,
        expand: str = "",
        max_results: int = 0,
    ) -> list[dict]:
        """Paginated JQL search returning issue JSON objects."""
        results: list[dict] = []
        start_at = 0
        page_size = 50

        default_fields = [
            "summary", "description", "status", "issuetype", "priority",
            "assignee", "reporter", "labels", "components", "fixVersions",
            "created", "updated", "resolutiondate", "resolution",
            "parent", "subtasks", "issuelinks", "comment", "attachment",
        ]

        params: dict[str, Any] = {
            "jql": jql,
            "maxResults": page_size,
            "fields": ",".join(fields or default_fields),
        }
        if expand:
            params["expand"] = expand

        while True:
            params["startAt"] = start_at
            data = await self._get("/search", params)
            issues = data.get("issues", [])
            results.extend(issues)

            if max_results and len(results) >= max_results:
                return results[:max_results]
            if start_at + len(issues) >= data.get("total", 0) or not issues:
                break
            start_at += len(issues)

        return results

    # ── Single issue ──────────────────────────────────────────────────────

    async def get_issue(
        self,
        issue_key: str,
        *,
        fields: list[str] | None = None,
        expand: str = "renderedFields",
    ) -> dict:
        params: dict[str, Any] = {}
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = expand
        return await self._get(f"/issue/{issue_key}", params)

    # ── Comments ──────────────────────────────────────────────────────────

    async def get_comments(
        self, issue_key: str, *, max_results: int = 0
    ) -> list[dict]:
        """Get all comments on an issue."""
        results: list[dict] = []
        start_at = 0

        while True:
            data = await self._get(
                f"/issue/{issue_key}/comment",
                {"startAt": start_at, "maxResults": 50},
            )
            comments = data.get("comments", [])
            results.extend(comments)
            if max_results and len(results) >= max_results:
                return results[:max_results]
            if start_at + len(comments) >= data.get("total", 0) or not comments:
                break
            start_at += len(comments)

        return results

    # ── Attachments ───────────────────────────────────────────────────────

    async def get_attachments(self, issue_key: str) -> list[dict]:
        """Get attachment metadata from the issue fields."""
        issue = await self.get_issue(issue_key, fields=["attachment"])
        return issue.get("fields", {}).get("attachment", [])

    async def download_attachment(self, url: str) -> bytes:
        return await self._download(url)

    # ── Worklogs ──────────────────────────────────────────────────────────

    async def get_worklogs(self, issue_key: str) -> list[dict]:
        data = await self._get(f"/issue/{issue_key}/worklog")
        return data.get("worklogs", [])

    # ── Changelogs ────────────────────────────────────────────────────────

    async def get_changelogs(
        self, issue_key: str, *, max_results: int = 100
    ) -> list[dict]:
        data = await self._get(
            f"/issue/{issue_key}/changelog",
            {"maxResults": max_results},
        )
        return data.get("values", [])
