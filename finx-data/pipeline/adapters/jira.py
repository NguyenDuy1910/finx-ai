"""Jira source adapter — multi-type content discovery.

Uses the Jira Cloud REST API v2 to search issues by project/JQL and
yield separate ``RawDocument`` instances for:
- Issues (with full fields)
- Comments (one per comment, linked to parent issue)
- Attachments (binary saved to ``ArtifactStore``)
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
from typing import Any, Iterator

from .base import BaseAdapter, RawDocument
from .jira_client import JiraV2Client
from pipeline.storage import ArtifactStore, create_artifact_store

log = logging.getLogger("finx-data.adapter.jira")

_DEFAULT_CONCURRENCY = 8


class JiraAdapter(BaseAdapter):
    """Fetch issues, comments, and attachments from Jira projects."""

    source_system = "jira"

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
        project_keys: list[str] | None = None,
        jql: str | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
        artifact_store: ArtifactStore | None = None,
        include_comments: bool = True,
        include_attachments: bool = True,
    ):
        self.base_url = base_url or os.environ.get("JIRA_URL", "")
        self.username = username or os.environ.get("JIRA_USERNAME", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")
        self.project_keys = project_keys or [
            s.strip()
            for s in os.environ.get("JIRA_PROJECT_KEYS", "").split(",")
            if s.strip()
        ]
        self.jql = jql
        self.concurrency = max(1, concurrency)
        self.artifact_store = artifact_store or create_artifact_store()
        self.include_comments = include_comments
        self.include_attachments = include_attachments

    def test_connection(self) -> bool:
        try:
            async def _test():
                async with JiraV2Client(
                    self.base_url, self.username, self.api_token, concurrency=1,
                ) as client:
                    results = await client.search_issues("order by created DESC", max_results=1)
                    return True
            return asyncio.run(_test())
        except Exception as exc:
            log.warning("Jira connection test failed: %s", exc)
            return False

    def fetch(self, **kwargs: Any) -> Iterator[RawDocument]:
        limit = kwargs.get("limit", 5000)
        docs = asyncio.run(self._fetch_all(limit=limit))
        yield from docs

    async def _fetch_all(self, *, limit: int = 5000) -> list[RawDocument]:
        results: list[RawDocument] = []

        async with JiraV2Client(
            self.base_url, self.username, self.api_token,
            concurrency=self.concurrency,
        ) as client:

            # Build JQL
            if self.jql:
                jql = self.jql
            elif self.project_keys:
                projects = ", ".join(f'"{k}"' for k in self.project_keys)
                jql = f"project in ({projects}) ORDER BY updated DESC"
            else:
                log.warning("No Jira project keys or JQL configured")
                return results

            issues = await client.search_issues(jql, max_results=limit)
            log.info("Fetched %d issues", len(issues))

            for issue in issues:
                issue_docs = await self._process_issue(client, issue)
                results.extend(issue_docs)

        log.info("Total Jira RawDocuments: %d", len(results))
        return results

    async def _process_issue(
        self, client: JiraV2Client, issue: dict
    ) -> list[RawDocument]:
        docs: list[RawDocument] = []
        fields = issue.get("fields", {})
        issue_key = issue.get("key", "")
        issue_id = str(issue.get("id", ""))

        # Extract fields
        summary = fields.get("summary", "")
        description = fields.get("description", "") or ""
        status = _nested_name(fields.get("status"))
        issue_type = _nested_name(fields.get("issuetype"))
        priority = _nested_name(fields.get("priority"))
        assignee = _nested_name(fields.get("assignee"), key="displayName")
        reporter = _nested_name(fields.get("reporter"), key="displayName")
        labels = fields.get("labels", [])
        components = [c.get("name", "") for c in fields.get("components", [])]
        fix_versions = [v.get("name", "") for v in fields.get("fixVersions", [])]
        created = fields.get("created", "")
        updated = fields.get("updated", "")
        resolved = fields.get("resolutiondate", "")
        resolution = _nested_name(fields.get("resolution"))

        # Parent / subtasks / links
        parent_key = ""
        parent_obj = fields.get("parent")
        if parent_obj:
            parent_key = parent_obj.get("key", "")
        subtasks = [s.get("key", "") for s in fields.get("subtasks", [])]
        linked_issues = []
        for link in fields.get("issuelinks", []):
            if "outwardIssue" in link:
                linked_issues.append({
                    "type": link.get("type", {}).get("outward", ""),
                    "key": link["outwardIssue"].get("key", ""),
                })
            if "inwardIssue" in link:
                linked_issues.append({
                    "type": link.get("type", {}).get("inward", ""),
                    "key": link["inwardIssue"].get("key", ""),
                })

        project_key = issue_key.rsplit("-", 1)[0] if "-" in issue_key else ""
        url = f"{client.base_url}/browse/{issue_key}"

        metadata = {
            "content_id": issue_id,
            "content_type": "issue",
            "issue_key": issue_key,
            "project_key": project_key,
            "status": status,
            "issue_type": issue_type,
            "priority": priority,
            "assignee": assignee,
            "reporter": reporter,
            "labels": labels,
            "components": components,
            "fix_versions": fix_versions,
            "created": created,
            "updated": updated,
            "resolved": resolved,
            "resolution": resolution,
            "parent_key": parent_key,
            "subtasks": subtasks,
            "linked_issues": linked_issues,
        }

        # Yield the issue itself
        docs.append(RawDocument(
            source_system=self.source_system,
            source_uri=url,
            source_id=issue_key,
            title=f"[{issue_key}] {summary}",
            raw_content=description,
            content_type="issue",
            metadata=metadata,
        ))

        # ── Comments ──────────────────────────────────────────────────
        if self.include_comments:
            comments = fields.get("comment", {}).get("comments", [])
            for comment in comments:
                comment_id = str(comment.get("id", ""))
                comment_body = comment.get("body", "")
                comment_author = _nested_name(comment.get("author"), key="displayName")
                comment_created = comment.get("created", "")
                comment_updated = comment.get("updated", "")

                docs.append(RawDocument(
                    source_system=self.source_system,
                    source_uri=f"{url}?focusedCommentId={comment_id}",
                    source_id=comment_id,
                    title=f"Comment on {issue_key} by {comment_author}",
                    raw_content=comment_body,
                    content_type="comment",
                    parent_id=issue_key,
                    parent_type="issue",
                    metadata={
                        "content_id": comment_id,
                        "content_type": "comment",
                        "parent_content_id": issue_key,
                        "parent_content_type": "issue",
                        "author": comment_author,
                        "created": comment_created,
                        "updated": comment_updated,
                        "project_key": project_key,
                    },
                ))

        # ── Attachments ───────────────────────────────────────────────
        if self.include_attachments:
            attachments = fields.get("attachment", [])
            for att in attachments:
                att_id = str(att.get("id", ""))
                att_filename = att.get("filename", "")
                att_url = att.get("content", "")
                att_mime = att.get("mimeType", "") or _guess_mime(att_filename)
                att_size = att.get("size", 0)
                att_author = _nested_name(att.get("author"), key="displayName")

                # Download and persist
                artifact_uri = ""
                if att_url:
                    try:
                        binary = await client.download_attachment(att_url)
                        artifact_uri = self.artifact_store.save(
                            content_id=att_id, filename=att_filename, data=binary,
                        )
                    except Exception as exc:
                        log.warning("Failed to download Jira attachment %s: %s", att_filename, exc)

                docs.append(RawDocument(
                    source_system=self.source_system,
                    source_uri=f"{url}/attachments/{att_id}",
                    source_id=att_id,
                    title=att_filename,
                    content_type="attachment",
                    parent_id=issue_key,
                    parent_type="issue",
                    mime_type=att_mime,
                    metadata={
                        "content_id": att_id,
                        "content_type": "attachment",
                        "parent_content_id": issue_key,
                        "parent_content_type": "issue",
                        "filename": att_filename,
                        "media_type": att_mime,
                        "file_size": att_size,
                        "artifact_uri": artifact_uri,
                        "author": att_author,
                        "project_key": project_key,
                    },
                ))

        return docs


def _nested_name(obj: dict | None, key: str = "name") -> str:
    if not obj or not isinstance(obj, dict):
        return ""
    return obj.get(key, "")


def _guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"
