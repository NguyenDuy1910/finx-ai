"""Confluence Cloud v2 REST API client.

Async HTTP client wrapping the ``/wiki/api/v2/`` endpoints for pages,
blog posts, comments, attachments, labels, ancestors, body conversion,
and CQL search.  Uses ``httpx.AsyncClient`` with Basic auth, semaphore-
based rate limiting, and exponential backoff on transient errors.

Reference: https://developer.atlassian.com/cloud/confluence/rest/v2/
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any

import httpx

log = logging.getLogger("finx-data.confluence-v2")

# Confluece v2 returns at most 250 items per page.
_MAX_PAGE_SIZE = 250
_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds


class ConfluenceV2Client:
    """Async client for the Confluence Cloud v2 REST API.

    Env vars
    --------
    CONFLUENCE_URL          Base URL  (e.g. ``https://org.atlassian.net``)
    CONFLUENCE_USERNAME     Atlassian account email
    CONFLUENCE_API_TOKEN    API token from id.atlassian.com
    """

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
        concurrency: int = 8,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or os.environ.get("CONFLUENCE_URL", "")).rstrip("/")
        self._username = username or os.environ.get("CONFLUENCE_USERNAME", "")
        self._token = api_token or os.environ.get("CONFLUENCE_API_TOKEN", "")
        self._sem = asyncio.Semaphore(concurrency)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def __aenter__(self) -> "ConfluenceV2Client":
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/wiki/api/v2",
            headers=self._auth_headers(),
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _auth_headers(self) -> dict[str, str]:
        cred = base64.b64encode(f"{self._username}:{self._token}".encode()).decode()
        return {
            "Authorization": f"Basic {cred}",
            "Accept": "application/json",
        }

    # ── low-level request ─────────────────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with semaphore rate-limit and retry."""
        assert self._client is not None, "Use `async with` to open the client"
        async with self._sem:
            return await self._request_with_retry("GET", path, params=params)

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        content: bytes | None = None,
    ) -> dict | bytes:
        assert self._client is not None
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.request(
                    method, path, params=params, content=content,
                )
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", _BACKOFF_BASE * (2 ** attempt)))
                    log.warning("Rate-limited (429), retrying after %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                if resp.headers.get("content-type", "").startswith("application/json"):
                    return resp.json()
                return resp.content
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    log.warning("Request %s %s failed (%s), retry in %.1fs", method, path, exc, wait)
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    async def _download(self, url: str) -> bytes:
        """Download raw bytes from an absolute URL (for attachments)."""
        assert self._client is not None
        async with self._sem:
            async with httpx.AsyncClient(
                headers=self._auth_headers(),
                timeout=self._timeout,
                follow_redirects=True,
            ) as dl_client:
                for attempt in range(_MAX_RETRIES):
                    try:
                        resp = await dl_client.get(url)
                        resp.raise_for_status()
                        return resp.content
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code < 500 or attempt >= _MAX_RETRIES - 1:
                            raise
                        await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))
                    except httpx.TransportError as exc:
                        if attempt >= _MAX_RETRIES - 1:
                            raise
                        await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))

    # ── pagination helper ─────────────────────────────────────────────────

    async def _paginate(
        self, path: str, params: dict | None = None, *, limit: int = 0
    ) -> list[dict]:
        """Auto-paginate a v2 list endpoint using cursor-based pagination.

        Args:
            path: API path (e.g. ``/spaces``).
            params: Initial query params (will be mutated with cursor).
            limit: Max results to return (0 = all).
        """
        params = dict(params or {})
        params.setdefault("limit", min(_MAX_PAGE_SIZE, limit or _MAX_PAGE_SIZE))
        results: list[dict] = []

        while True:
            data = await self._get(path, params)
            batch = data.get("results", [])
            results.extend(batch)

            if limit and len(results) >= limit:
                return results[:limit]

            # Cursor-based pagination
            links = data.get("_links", {})
            next_url = links.get("next")
            if not next_url or not batch:
                break

            # Extract cursor from next link
            if "cursor=" in next_url:
                cursor = next_url.split("cursor=")[1].split("&")[0]
                params["cursor"] = cursor
            else:
                break

        return results

    # ── Spaces ────────────────────────────────────────────────────────────

    async def list_spaces(
        self,
        *,
        keys: list[str] | None = None,
        limit: int = 0,
    ) -> list[dict]:
        """List spaces, optionally filtered by key."""
        params: dict[str, Any] = {}
        if keys:
            params["keys"] = ",".join(keys)
        return await self._paginate("/spaces", params, limit=limit)

    async def get_space(self, space_id: str) -> dict:
        return await self._get(f"/spaces/{space_id}")

    # ── Pages ─────────────────────────────────────────────────────────────

    async def list_pages(
        self,
        space_id: str,
        *,
        status: str = "current",
        sort: str = "-modified-date",
        limit: int = 0,
        body_format: str | None = None,
    ) -> list[dict]:
        """List pages in a space.

        Args:
            space_id: Confluence space ID (numeric).
            status: ``current``, ``archived``, ``trashed``, or ``any``.
            sort: Sort order (v2 default: ``id``).
            limit: Max pages, 0 = all.
            body_format: If set, include body in this format (e.g. ``storage``).
        """
        params: dict[str, Any] = {
            "space-id": space_id,
            "status": status,
            "sort": sort,
        }
        if body_format:
            params["body-format"] = body_format
        return await self._paginate("/pages", params, limit=limit)

    async def get_page(
        self,
        page_id: str,
        *,
        body_format: str = "storage",
        include_labels: bool = True,
        include_version: bool = True,
    ) -> dict:
        """Get a single page with body.

        Args:
            page_id: Confluence page ID.
            body_format: Body representation to return.
            include_labels: Include labels in the response.
            include_version: Include version info.
        """
        params: dict[str, Any] = {"body-format": body_format}
        return await self._get(f"/pages/{page_id}", params)

    # ── Blog Posts ────────────────────────────────────────────────────────

    async def list_blogposts(
        self,
        space_id: str,
        *,
        status: str = "current",
        sort: str = "-modified-date",
        limit: int = 0,
        body_format: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "space-id": space_id,
            "status": status,
            "sort": sort,
        }
        if body_format:
            params["body-format"] = body_format
        return await self._paginate("/blogposts", params, limit=limit)

    async def get_blogpost(
        self,
        blogpost_id: str,
        *,
        body_format: str = "storage",
    ) -> dict:
        params: dict[str, Any] = {"body-format": body_format}
        return await self._get(f"/blogposts/{blogpost_id}", params)

    # ── Comments ──────────────────────────────────────────────────────────

    async def get_page_inline_comments(
        self, page_id: str, *, limit: int = 0, body_format: str = "storage"
    ) -> list[dict]:
        params: dict[str, Any] = {"body-format": body_format}
        return await self._paginate(
            f"/pages/{page_id}/inline-comments", params, limit=limit
        )

    async def get_page_footer_comments(
        self, page_id: str, *, limit: int = 0, body_format: str = "storage"
    ) -> list[dict]:
        params: dict[str, Any] = {"body-format": body_format}
        return await self._paginate(
            f"/pages/{page_id}/footer-comments", params, limit=limit
        )

    async def get_blogpost_inline_comments(
        self, blogpost_id: str, *, limit: int = 0, body_format: str = "storage"
    ) -> list[dict]:
        params: dict[str, Any] = {"body-format": body_format}
        return await self._paginate(
            f"/blogposts/{blogpost_id}/inline-comments", params, limit=limit
        )

    async def get_blogpost_footer_comments(
        self, blogpost_id: str, *, limit: int = 0, body_format: str = "storage"
    ) -> list[dict]:
        params: dict[str, Any] = {"body-format": body_format}
        return await self._paginate(
            f"/blogposts/{blogpost_id}/footer-comments", params, limit=limit
        )

    # ── Attachments ───────────────────────────────────────────────────────

    async def get_page_attachments(
        self, page_id: str, *, limit: int = 0
    ) -> list[dict]:
        return await self._paginate(f"/pages/{page_id}/attachments", limit=limit)

    async def get_blogpost_attachments(
        self, blogpost_id: str, *, limit: int = 0
    ) -> list[dict]:
        return await self._paginate(
            f"/blogposts/{blogpost_id}/attachments", limit=limit
        )

    async def download_attachment(self, download_url: str) -> bytes:
        """Download attachment binary content.

        Args:
            download_url: The ``downloadLink`` from the attachment metadata.
                If relative, it's resolved against ``base_url/wiki``.
        """
        if download_url.startswith("/"):
            download_url = f"{self.base_url}/wiki{download_url}"
        return await self._download(download_url)

    # ── Labels ────────────────────────────────────────────────────────────

    async def get_page_labels(
        self, page_id: str, *, limit: int = 0
    ) -> list[dict]:
        return await self._paginate(f"/pages/{page_id}/labels", limit=limit)

    async def get_blogpost_labels(
        self, blogpost_id: str, *, limit: int = 0
    ) -> list[dict]:
        return await self._paginate(f"/blogposts/{blogpost_id}/labels", limit=limit)

    # ── Ancestors ─────────────────────────────────────────────────────────

    async def get_page_ancestors(self, page_id: str) -> list[dict]:
        """Get the ancestor chain for a page (root → ... → parent)."""
        data = await self._get(f"/pages/{page_id}/ancestors")
        return data.get("results", data) if isinstance(data, dict) else data

    # ── Body Conversion ───────────────────────────────────────────────────

    async def convert_body(
        self,
        content_id: str,
        *,
        from_repr: str = "storage",
        to_repr: str = "export_view",
    ) -> str:
        """Convert a page/blogpost body between representations.

        Uses the v1 content body convert endpoint (still available for v2 content IDs).

        Returns:
            The converted body HTML/ADF string.
        """
        assert self._client is not None
        # v2 does not have a native convert endpoint; use the v1 fallback
        async with self._sem:
            resp = await self._client.request(
                "GET",
                f"../../rest/api/content/{content_id}",
                params={"expand": f"body.{to_repr}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("body", {}).get(to_repr, {}).get("value", "")

    # ── CQL Search ────────────────────────────────────────────────────────

    async def cql_search(
        self,
        cql: str,
        *,
        limit: int = 0,
        expand: str = "",
    ) -> list[dict]:
        """Run a CQL search query.

        This uses the v1 search endpoint (``/wiki/rest/api/search``) which
        is the only CQL-capable endpoint in Confluence Cloud.
        """
        assert self._client is not None
        params: dict[str, Any] = {"cql": cql, "limit": min(50, limit or 50)}
        if expand:
            params["expand"] = expand

        results: list[dict] = []
        start = 0
        while True:
            params["start"] = start
            async with self._sem:
                resp = await self._client.request(
                    "GET", "../../rest/api/search", params=params
                )
                resp.raise_for_status()
                data = resp.json()

            batch = data.get("results", [])
            results.extend(batch)
            if limit and len(results) >= limit:
                return results[:limit]
            if data.get("size", 0) < params["limit"] or not batch:
                break
            start += len(batch)

        return results
