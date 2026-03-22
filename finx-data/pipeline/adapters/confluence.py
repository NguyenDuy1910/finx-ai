"""Confluence source adapter — multi-type content graph discovery.

Uses the Confluence Cloud v2 REST API to enumerate and fetch all content
types (pages, blog posts, comments, attachments) per space. Each content
object is yielded as a separate ``RawDocument`` with explicit
``content_type``, ``parent_id``, and full Confluence metadata.

Binary attachments are persisted to an ``ArtifactStore`` and referenced
via ``metadata["artifact_uri"]`` — they are NOT carried in memory.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Iterator

from .base import BaseAdapter, RawDocument
from .confluence_v2_client import ConfluenceV2Client
from pipeline.storage import ArtifactStore, create_artifact_store

log = logging.getLogger("finx-data.adapter.confluence")

_DEFAULT_CONCURRENCY = 8


class ConfluenceAdapter(BaseAdapter):
    """Fetch all content types from one or more Confluence spaces.

    Yields separate ``RawDocument`` instances for:
    - pages
    - blog posts
    - inline/footer comments (per page and per blogpost)
    - attachments (binary saved to ``ArtifactStore``)
    """

    source_system = "confluence"

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
        space_keys: list[str] | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
        artifact_store: ArtifactStore | None = None,
        include_comments: bool = True,
        include_attachments: bool = True,
        include_blogposts: bool = True,
        body_format: str = "storage",
        page_url: str | None = None,
        limit: int = 2000,
        progress_file: str | Path | None = None,
    ):
        self.base_url = (base_url or os.environ.get("CONFLUENCE_URL", "")).rstrip("/")
        self.username = username or os.environ.get("CONFLUENCE_USERNAME", "")
        self.api_token = api_token or os.environ.get("CONFLUENCE_API_TOKEN", "")
        self.space_keys = space_keys or [
            s.strip()
            for s in os.environ.get("CONFLUENCE_SPACE_KEYS", "DATA").split(",")
            if s.strip()
        ]
        self.concurrency = max(1, concurrency)
        self.artifact_store = artifact_store or create_artifact_store()
        self.include_comments = include_comments
        self.include_attachments = include_attachments
        self.include_blogposts = include_blogposts
        self.body_format = body_format
        self.page_url = page_url
        self.limit = limit
        self._progress_file = Path(progress_file) if progress_file else None

    def test_connection(self) -> bool:
        try:
            async def _test():
                async with ConfluenceV2Client(
                    self.base_url, self.username, self.api_token, concurrency=1,
                ) as client:
                    spaces = await client.list_spaces(limit=1)
                    return len(spaces) > 0
            return asyncio.run(_test())
        except Exception as exc:
            log.warning("Confluence connection test failed: %s", exc)
            return False

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        """Yield RawDocuments for all content types across configured spaces.

        Processes each page fully (body + comments + attachments) before
        moving to the next page. Skips pages whose main document was
        already processed in a previous run (checked against progress file).

        Keyword args
        ------------
        page_url : str | None
            If set, fetch exactly one page by URL (legacy compat).
        limit : int
            Max pages per space (default 2000).
        """
        page_url: str | None = kwargs.get("page_url") or self.page_url
        limit = kwargs.get("limit", self.limit)

        # Single page mode — fetch everything at once
        if page_url:
            docs = asyncio.run(
                self._fetch_all(page_url=page_url, limit=limit)
            )
            yield from docs
            return

        # Phase 1: Discover content items (lightweight metadata only)
        content_plan = asyncio.run(self._discover_content(limit=limit))
        log.info("Discovered %d content items to process", len(content_plan))

        # Load already-processed IDs to skip API calls
        done_ids = self._load_done_ids()
        skipped = 0

        # Phase 2: Fetch and yield each content item fully before the next
        for item_info in content_plan:
            content_id = str(item_info["meta"].get("id", ""))
            space_key = item_info["space_key"]
            content_type = item_info["content_type"]
            title = item_info["meta"].get("title", "")

            # Skip if main document is already processed
            if done_ids:
                predicted_uri = self._build_source_uri(space_key, content_id, content_type)
                raw_key = f"{self.source_system}::{predicted_uri}"
                predicted_doc_id = hashlib.sha256(raw_key.encode()).hexdigest()
                if predicted_doc_id in done_ids:
                    log.debug("Skip (already processed): [%s] %s", content_type, title or content_id)
                    skipped += 1
                    continue

            log.info("Fetching %s: %s (%s)", content_type, title or content_id, content_id)
            try:
                docs = asyncio.run(self._fetch_single_item(item_info))
                yield from docs
            except Exception as exc:
                log.warning("Error fetching %s %s: %s", content_type, content_id, exc)

        if skipped:
            log.info("Skipped %d already-processed content items at adapter level", skipped)

    # ── async internals ───────────────────────────────────────────────────

    async def _fetch_all(
        self,
        *,
        page_url: str | None = None,
        limit: int = 2000,
    ) -> list[RawDocument]:
        """Fetch a single page by URL. Used only for single-page mode."""
        results: list[RawDocument] = []

        async with ConfluenceV2Client(
            self.base_url, self.username, self.api_token,
            concurrency=self.concurrency,
        ) as client:

            if page_url:
                page_meta = await self._resolve_page_url(client, page_url)
                if page_meta:
                    space_id = str(page_meta.get("spaceId", ""))
                    try:
                        space_info = await client.get_space(space_id)
                        space_key = space_info.get("key", space_id)
                    except Exception:
                        space_key = space_id
                    page_docs = await self._process_content_item(
                        client, page_meta, "page",
                        space_key=space_key,
                        space_id=space_id,
                    )
                    results.extend(page_docs)

        return results

    async def _discover_content(
        self, *, limit: int = 2000,
    ) -> list[dict]:
        """Discover all content items (lightweight metadata only, no bodies)."""
        items: list[dict] = []

        async with ConfluenceV2Client(
            self.base_url, self.username, self.api_token,
            concurrency=self.concurrency,
        ) as client:
            spaces = await client.list_spaces(keys=self.space_keys)
            log.info("Discovered %d spaces: %s", len(spaces), [s.get("key") for s in spaces])

            for space in spaces:
                space_id = space.get("id", "")
                space_key = space.get("key", "")

                # ── Pages ───────────────────────────────────────────────
                pages = await client.list_pages(space_id, limit=limit)
                log.info("Space %s: %d pages", space_key, len(pages))
                for page_meta in pages:
                    items.append({
                        "meta": page_meta,
                        "content_type": "page",
                        "space_key": space_key,
                        "space_id": space_id,
                    })

                # ── Blog Posts ──────────────────────────────────────────
                if self.include_blogposts:
                    blogposts = await client.list_blogposts(space_id, limit=limit)
                    log.info("Space %s: %d blogposts", space_key, len(blogposts))
                    for bp_meta in blogposts:
                        items.append({
                            "meta": bp_meta,
                            "content_type": "blogpost",
                            "space_key": space_key,
                            "space_id": space_id,
                        })

        return items

    async def _fetch_single_item(self, item_info: dict) -> list[RawDocument]:
        """Fetch one content item fully (body + comments + attachments)."""
        async with ConfluenceV2Client(
            self.base_url, self.username, self.api_token,
            concurrency=self.concurrency,
        ) as client:
            return await self._process_content_item(
                client,
                item_info["meta"],
                item_info["content_type"],
                item_info["space_key"],
                item_info["space_id"],
            )

    async def _process_content_item(
        self,
        client: ConfluenceV2Client,
        item: dict,
        content_type: str,
        space_key: str,
        space_id: str,
    ) -> list[RawDocument]:
        """Process one page or blogpost: fetch body, comments, attachments."""
        docs: list[RawDocument] = []
        content_id = str(item.get("id", ""))
        title = item.get("title", "")

        # Fetch full body
        try:
            if content_type == "page":
                full = await client.get_page(content_id, body_format=self.body_format)
            else:
                full = await client.get_blogpost(content_id, body_format=self.body_format)
        except Exception as exc:
            log.warning("Failed to fetch %s %s: %s", content_type, content_id, exc)
            return docs

        body_html = full.get("body", {}).get(self.body_format, {}).get("value", "")
        version_info = full.get("version", {})
        version_num = version_info.get("number", 0) if isinstance(version_info, dict) else 0
        author = _extract_author(full)
        created_at = full.get("createdAt", "")
        modified_at = version_info.get("createdAt", "") if isinstance(version_info, dict) else ""

        # Fetch labels
        try:
            if content_type == "page":
                labels_data = await client.get_page_labels(content_id)
            else:
                labels_data = await client.get_blogpost_labels(content_id)
            labels = [lb.get("name", "") for lb in labels_data if lb.get("name")]
        except Exception:
            labels = []

        # Fetch ancestors (pages only)
        ancestors = []
        if content_type == "page":
            try:
                ancestors_data = await client.get_page_ancestors(content_id)
                ancestors = [
                    {"id": str(a.get("id", "")), "title": a.get("title", "")}
                    for a in ancestors_data
                ]
            except Exception:
                pass

        # Build canonical URL
        url = f"{client.base_url}/wiki/spaces/{space_key}/pages/{content_id}"
        if content_type == "blogpost":
            url = f"{client.base_url}/wiki/spaces/{space_key}/blog/{content_id}"

        metadata = {
            "space_key": space_key,
            "space_id": space_id,
            "content_id": content_id,
            "content_type": content_type,
            "version": version_num,
            "author": author,
            "created_at": created_at,
            "last_modified": modified_at,
            "labels": labels,
            "ancestors": ancestors,
            "body_representation": self.body_format,
            "confluence_url": url,
        }

        # Yield the main content document
        docs.append(RawDocument(
            source_system=self.source_system,
            source_uri=url,
            source_id=content_id,
            title=title,
            raw_content="",
            raw_html=body_html,
            content_type=content_type,
            body_representation=self.body_format,
            version=version_num,
            metadata=metadata,
        ))

        # ── Comments ──────────────────────────────────────────────────
        if self.include_comments:
            comment_docs = await self._fetch_comments(
                client, content_id, content_type, space_key, space_id, title, url,
            )
            docs.extend(comment_docs)

        # ── Attachments ───────────────────────────────────────────────
        if self.include_attachments:
            att_docs = await self._fetch_attachments(
                client, content_id, content_type, space_key, space_id, title, url,
            )
            docs.extend(att_docs)

        return docs

    async def _fetch_comments(
        self,
        client: ConfluenceV2Client,
        parent_id: str,
        parent_type: str,
        space_key: str,
        space_id: str,
        parent_title: str,
        parent_url: str,
    ) -> list[RawDocument]:
        """Fetch inline + footer comments for a page or blogpost."""
        docs: list[RawDocument] = []

        for location, fetch_fn in self._comment_fetchers(client, parent_id, parent_type):
            try:
                comments = await fetch_fn()
            except Exception as exc:
                log.debug("Failed to fetch %s comments for %s: %s", location, parent_id, exc)
                continue

            for comment in comments:
                comment_id = str(comment.get("id", ""))
                comment_body = comment.get("body", {}).get("storage", {}).get("value", "")
                comment_author = _extract_author(comment)
                comment_created = comment.get("createdAt", "")

                docs.append(RawDocument(
                    source_system=self.source_system,
                    source_uri=f"{parent_url}#comment-{comment_id}",
                    source_id=comment_id,
                    title=f"Comment on: {parent_title}",
                    raw_content="",
                    raw_html=comment_body,
                    content_type="comment",
                    parent_id=parent_id,
                    parent_type=parent_type,
                    metadata={
                        "space_key": space_key,
                        "space_id": space_id,
                        "content_id": comment_id,
                        "content_type": "comment",
                        "comment_location": location,
                        "parent_content_id": parent_id,
                        "parent_content_type": parent_type,
                        "parent_title": parent_title,
                        "author": comment_author,
                        "created_at": comment_created,
                    },
                ))

        return docs

    def _comment_fetchers(self, client, parent_id, parent_type):
        """Yield (location, async_fetch_fn) tuples for comment endpoints."""
        if parent_type == "page":
            yield "inline", lambda: client.get_page_inline_comments(parent_id)
            yield "footer", lambda: client.get_page_footer_comments(parent_id)
        elif parent_type == "blogpost":
            yield "inline", lambda: client.get_blogpost_inline_comments(parent_id)
            yield "footer", lambda: client.get_blogpost_footer_comments(parent_id)

    async def _fetch_attachments(
        self,
        client: ConfluenceV2Client,
        parent_id: str,
        parent_type: str,
        space_key: str,
        space_id: str,
        parent_title: str,
        parent_url: str,
    ) -> list[RawDocument]:
        """Fetch attachment metadata + download binaries to artifact store."""
        docs: list[RawDocument] = []

        try:
            if parent_type == "page":
                attachments = await client.get_page_attachments(parent_id)
            else:
                attachments = await client.get_blogpost_attachments(parent_id)
        except Exception as exc:
            log.debug("Failed to fetch attachments for %s: %s", parent_id, exc)
            return docs

        for att in attachments:
            att_id = str(att.get("id", ""))
            att_title = att.get("title", "")
            download_link = att.get("downloadLink", "")
            media_type = att.get("mediaType", "") or _guess_mime(att_title)
            file_size = att.get("fileSize", 0)

            # Download and persist binary (skip if already in artifact store)
            artifact_uri = ""
            if download_link:
                # Predict the artifact_uri to check if already downloaded
                predicted_uri = _predict_artifact_uri(att_id, att_title)
                if predicted_uri and self.artifact_store.exists(predicted_uri):
                    artifact_uri = predicted_uri
                    log.debug("Artifact already exists, skipping download: %s", artifact_uri)
                else:
                    try:
                        binary = await client.download_attachment(download_link)
                        artifact_uri = self.artifact_store.save(
                            content_id=att_id, filename=att_title, data=binary,
                        )
                        log.debug("Saved attachment %s → %s (%d bytes)", att_title, artifact_uri, len(binary))
                    except BaseException as exc:
                        log.warning("Failed to download attachment %s: %s", att_title, exc)

            # Build proper Confluence download URL
            att_source_uri = f"{client.base_url}/wiki/download/attachments/{parent_id}/{att_title}"

            docs.append(RawDocument(
                source_system=self.source_system,
                source_uri=att_source_uri,
                source_id=att_id,
                title=att_title,
                raw_content="",
                raw_html="",
                content_type="attachment",
                parent_id=parent_id,
                parent_type=parent_type,
                mime_type=media_type,
                metadata={
                    "space_key": space_key,
                    "space_id": space_id,
                    "content_id": att_id,
                    "content_type": "attachment",
                    "parent_content_id": parent_id,
                    "parent_content_type": parent_type,
                    "parent_title": parent_title,
                    "parent_url": parent_url,
                    "filename": att_title,
                    "media_type": media_type,
                    "file_size": file_size,
                    "artifact_uri": artifact_uri,
                    "download_link": download_link,
                },
            ))

        return docs

    def _build_source_uri(self, space_key: str, content_id: str, content_type: str) -> str:
        """Build the source_uri for a content item (must match _process_content_item)."""
        if content_type == "blogpost":
            return f"{self.base_url}/wiki/spaces/{space_key}/blog/{content_id}"
        return f"{self.base_url}/wiki/spaces/{space_key}/pages/{content_id}"

    def _load_done_ids(self) -> set[str]:
        """Load already-processed document IDs from the progress file."""
        if not self._progress_file or not self._progress_file.exists():
            return set()
        try:
            data = json.loads(self._progress_file.read_text(encoding="utf-8"))
            ids = set(data.get("processed_ids", []))
            if ids:
                log.info("Loaded %d already-processed IDs from %s", len(ids), self._progress_file)
            return ids
        except Exception as exc:
            log.warning("Could not load progress file %s: %s", self._progress_file, exc)
            return set()

    async def _resolve_page_url(
        self, client: ConfluenceV2Client, page_url: str
    ) -> dict | None:
        """Extract page ID from URL and fetch page metadata.

        Returns a dict compatible with ``_process_content_item``
        (same shape as ``list_pages`` items).
        """
        import re
        m = re.search(r"/pages/(\d+)", page_url)
        if not m:
            log.error("Cannot extract page ID from URL: %s", page_url)
            return None
        page_id = m.group(1)

        try:
            full = await client.get_page(page_id, body_format=self.body_format)
        except Exception as exc:
            log.error("Failed to fetch page %s: %s", page_id, exc)
            return None

        # Inject the canonical URL so _process_content_item can use it
        full.setdefault("_links", {})["base"] = self.base_url
        return full


# ── helpers ───────────────────────────────────────────────────────────────────


def _extract_author(item: dict) -> str:
    """Extract author display name from a v2 content object."""
    version = item.get("version", {})
    if isinstance(version, dict):
        author_info = version.get("authorId", "")
        if author_info:
            return str(author_info)
    # Fallback: ownerId field
    return str(item.get("ownerId", ""))


def _guess_mime(filename: str) -> str:
    """Guess MIME type from filename extension."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _sanitize_for_artifact(name: str) -> str:
    """Mirror the artifact store's sanitization logic."""
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in name)


def _predict_artifact_uri(content_id: str, filename: str) -> str:
    """Predict the artifact_uri that the artifact store would produce."""
    safe_id = _sanitize_for_artifact(content_id)
    safe_name = _sanitize_for_artifact(filename)
    return f"{safe_id}/{safe_name}"
