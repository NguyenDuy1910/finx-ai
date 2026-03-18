from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agno.tools.mcp import MCPTools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Complete tool catalogue — all 72 tools from mcp-atlassian
# https://mcp-atlassian.soomiles.com/docs/tools-reference
# ---------------------------------------------------------------------------

# ── Confluence: Pages ──────────────────────────────────────────────────────
CONFLUENCE_PAGES_TOOLS: List[str] = [
    "confluence_search",
    "confluence_get_page",
    "confluence_get_page_children",
    "confluence_get_page_history",
    "confluence_create_page",
    "confluence_update_page",
    "confluence_move_page",
    "confluence_get_page_diff",
]

# ── Confluence: Comments & Labels ──────────────────────────────────────────
CONFLUENCE_COMMENTS_TOOLS: List[str] = [
    "confluence_get_comments",
    "confluence_add_comment",
    "confluence_reply_to_comment",
]

CONFLUENCE_LABELS_TOOLS: List[str] = [
    "confluence_get_labels",
    "confluence_add_label",
]

# ── Confluence: Users ──────────────────────────────────────────────────────
CONFLUENCE_USERS_TOOLS: List[str] = [
    "confluence_search_user",
]

# ── Confluence: Analytics ──────────────────────────────────────────────────
CONFLUENCE_ANALYTICS_TOOLS: List[str] = [
    "confluence_get_page_views",
]

# ── Confluence: Attachments ────────────────────────────────────────────────
CONFLUENCE_ATTACHMENTS_TOOLS: List[str] = [
    "confluence_upload_attachment",
    "confluence_upload_attachments",
    "confluence_get_attachments",
    "confluence_download_attachment",
    "confluence_download_content_attachments",
    "confluence_get_page_images",
]

# ── Jira: Issues ──────────────────────────────────────────────────────────
JIRA_ISSUES_TOOLS: List[str] = [
    "jira_get_issue",
    "jira_search",
    "jira_get_project_issues",
    "jira_create_issue",
    "jira_update_issue",
    "jira_batch_create_issues",
    "jira_batch_get_changelogs",
]

# ── Jira: Search & Fields ─────────────────────────────────────────────────
JIRA_FIELDS_TOOLS: List[str] = [
    "jira_search_fields",
    "jira_get_field_options",
]

# ── Jira: Comments ─────────────────────────────────────────────────────────
JIRA_COMMENTS_TOOLS: List[str] = [
    "jira_add_comment",
    "jira_edit_comment",
]

# ── Jira: Transitions ─────────────────────────────────────────────────────
JIRA_TRANSITIONS_TOOLS: List[str] = [
    "jira_get_transitions",
    "jira_transition_issue",
]

# ── Jira: Projects ─────────────────────────────────────────────────────────
JIRA_PROJECTS_TOOLS: List[str] = [
    "jira_get_all_projects",
    "jira_get_project_versions",
    "jira_get_project_components",
    "jira_create_version",
    "jira_batch_create_versions",
]

# ── Jira: Agile ────────────────────────────────────────────────────────────
JIRA_AGILE_TOOLS: List[str] = [
    "jira_get_agile_boards",
    "jira_get_board_issues",
    "jira_get_sprints_from_board",
    "jira_get_sprint_issues",
    "jira_create_sprint",
    "jira_update_sprint",
    "jira_add_issues_to_sprint",
]

# ── Jira: Links & Versions ────────────────────────────────────────────────
JIRA_LINKS_TOOLS: List[str] = [
    "jira_get_link_types",
    "jira_link_to_epic",
    "jira_create_issue_link",
    "jira_create_remote_issue_link",
    "jira_remove_issue_link",
]

# ── Jira: Worklogs ────────────────────────────────────────────────────────
JIRA_WORKLOG_TOOLS: List[str] = [
    "jira_get_worklog",
    "jira_add_worklog",
]

# ── Jira: Attachments ─────────────────────────────────────────────────────
JIRA_ATTACHMENTS_TOOLS: List[str] = [
    "jira_download_attachments",
    "jira_get_issue_images",
]

# ── Jira: Users ────────────────────────────────────────────────────────────
JIRA_USERS_TOOLS: List[str] = [
    "jira_get_user_profile",
]

# ── Jira: Watchers ─────────────────────────────────────────────────────────
JIRA_WATCHERS_TOOLS: List[str] = [
    "jira_get_issue_watchers",
    "jira_add_watcher",
    "jira_remove_watcher",
]

# ── Jira: Service Desk ────────────────────────────────────────────────────
JIRA_SERVICE_DESK_TOOLS: List[str] = [
    "jira_get_service_desk_for_project",
    "jira_get_service_desk_queues",
    "jira_get_queue_issues",
]

# ── Jira: Forms ────────────────────────────────────────────────────────────
JIRA_FORMS_TOOLS: List[str] = [
    "jira_get_issue_proforma_forms",
    "jira_get_proforma_form_details",
    "jira_update_proforma_form_answers",
]

# ── Jira: Metrics ──────────────────────────────────────────────────────────
JIRA_METRICS_TOOLS: List[str] = [
    "jira_get_issue_dates",
    "jira_get_issue_sla",
]

# ── Jira: Development ─────────────────────────────────────────────────────
JIRA_DEVELOPMENT_TOOLS: List[str] = [
    "jira_get_issue_development_info",
    "jira_get_issues_development_info",
]

# ---------------------------------------------------------------------------
# Composite groups
# ---------------------------------------------------------------------------

# All Confluence tools (23 tools)
CONFLUENCE_ALL_TOOLS: List[str] = (
    CONFLUENCE_PAGES_TOOLS
    + CONFLUENCE_COMMENTS_TOOLS
    + CONFLUENCE_LABELS_TOOLS
    + CONFLUENCE_USERS_TOOLS
    + CONFLUENCE_ANALYTICS_TOOLS
    + CONFLUENCE_ATTACHMENTS_TOOLS
)

# All Jira tools (49 tools)
JIRA_ALL_TOOLS: List[str] = (
    JIRA_ISSUES_TOOLS
    + JIRA_FIELDS_TOOLS
    + JIRA_COMMENTS_TOOLS
    + JIRA_TRANSITIONS_TOOLS
    + JIRA_PROJECTS_TOOLS
    + JIRA_AGILE_TOOLS
    + JIRA_LINKS_TOOLS
    + JIRA_WORKLOG_TOOLS
    + JIRA_ATTACHMENTS_TOOLS
    + JIRA_USERS_TOOLS
    + JIRA_WATCHERS_TOOLS
    + JIRA_SERVICE_DESK_TOOLS
    + JIRA_FORMS_TOOLS
    + JIRA_METRICS_TOOLS
    + JIRA_DEVELOPMENT_TOOLS
)

# All 72 tools
ATLASSIAN_ALL_TOOLS: List[str] = CONFLUENCE_ALL_TOOLS + JIRA_ALL_TOOLS

# ---------------------------------------------------------------------------
# Read-only subsets (backward-compatible)
# ---------------------------------------------------------------------------

CONFLUENCE_READ_TOOLS: List[str] = [
    "confluence_search",
    "confluence_get_page",
    "confluence_get_page_children",
    "confluence_get_page_history",
    "confluence_get_page_diff",
    "confluence_get_comments",
    "confluence_get_labels",
    "confluence_search_user",
    "confluence_get_page_views",
    "confluence_get_attachments",
    "confluence_download_attachment",
    "confluence_download_content_attachments",
    "confluence_get_page_images",
]

JIRA_READ_TOOLS: List[str] = [
    "jira_get_issue",
    "jira_search",
    "jira_get_project_issues",
    "jira_search_fields",
    "jira_get_field_options",
    "jira_get_transitions",
    "jira_get_all_projects",
    "jira_get_project_versions",
    "jira_get_project_components",
    "jira_get_agile_boards",
    "jira_get_board_issues",
    "jira_get_sprints_from_board",
    "jira_get_sprint_issues",
    "jira_get_link_types",
    "jira_get_worklog",
    "jira_download_attachments",
    "jira_get_issue_images",
    "jira_get_user_profile",
    "jira_get_issue_watchers",
    "jira_get_service_desk_for_project",
    "jira_get_service_desk_queues",
    "jira_get_queue_issues",
    "jira_get_issue_proforma_forms",
    "jira_get_proforma_form_details",
    "jira_get_issue_dates",
    "jira_get_issue_sla",
    "jira_get_issue_development_info",
    "jira_get_issues_development_info",
    "jira_batch_get_changelogs",
]

ATLASSIAN_READ_TOOLS: List[str] = CONFLUENCE_READ_TOOLS + JIRA_READ_TOOLS

# ---------------------------------------------------------------------------
# Write-only subsets
# ---------------------------------------------------------------------------

CONFLUENCE_WRITE_TOOLS: List[str] = [
    "confluence_create_page",
    "confluence_update_page",
    "confluence_move_page",
    "confluence_add_comment",
    "confluence_reply_to_comment",
    "confluence_add_label",
    "confluence_upload_attachment",
    "confluence_upload_attachments",
]

JIRA_WRITE_TOOLS: List[str] = [
    "jira_create_issue",
    "jira_update_issue",
    "jira_batch_create_issues",
    "jira_add_comment",
    "jira_edit_comment",
    "jira_transition_issue",
    "jira_create_version",
    "jira_batch_create_versions",
    "jira_create_sprint",
    "jira_update_sprint",
    "jira_add_issues_to_sprint",
    "jira_link_to_epic",
    "jira_create_issue_link",
    "jira_create_remote_issue_link",
    "jira_remove_issue_link",
    "jira_add_worklog",
    "jira_add_watcher",
    "jira_remove_watcher",
    "jira_update_proforma_form_answers",
]

ATLASSIAN_WRITE_TOOLS: List[str] = CONFLUENCE_WRITE_TOOLS + JIRA_WRITE_TOOLS


def _build_env(
    confluence_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_token: Optional[str] = None,
    jira_url: Optional[str] = None,
    jira_username: Optional[str] = None,
    jira_api_token: Optional[str] = None,
    read_only: bool = False,
) -> Dict[str, str]:
    env: Dict[str, str] = {
        # Enable every toolset so agents can access all 72 tools;
        # fine-grained filtering is done via include_tools / exclude_tools.
        "TOOLSETS": "all",
    }

    if read_only:
        env["READ_ONLY_MODE"] = "true"

    url = confluence_url or os.getenv("CONFLUENCE_URL", "")
    if url:
        env["CONFLUENCE_URL"] = url
        env["CONFLUENCE_USERNAME"] = confluence_username or os.getenv("CONFLUENCE_USERNAME", "")
        env["CONFLUENCE_API_TOKEN"] = confluence_api_token or os.getenv(
            "CONFLUENCE_API_TOKEN", os.getenv("CONFLUENCE_API_KEY", "")
        )

    # Jira (optional)
    jurl = jira_url or os.getenv("JIRA_URL", "")
    if jurl:
        env["JIRA_URL"] = jurl
        env["JIRA_USERNAME"] = jira_username or os.getenv("JIRA_USERNAME", "")
        env["JIRA_API_TOKEN"] = jira_api_token or os.getenv("JIRA_API_TOKEN", "")

    return env


def create_mcp_atlassian_tools(
    *,
    confluence_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_token: Optional[str] = None,
    jira_url: Optional[str] = None,
    jira_username: Optional[str] = None,
    jira_api_token: Optional[str] = None,
    include_tools: Optional[List[str]] = None,
    exclude_tools: Optional[List[str]] = None,
    read_only: bool = False,
    timeout_seconds: int = 30,
) -> MCPTools:
    """Create an ``MCPTools`` instance backed by the ``mcp-atlassian`` stdio server.

    The returned object must be used as an **async context manager**::

        mcp_tools = create_mcp_atlassian_tools()
        async with mcp_tools:
            agent = Agent(..., tools=[mcp_tools])
            await agent.aprint_response(...)

    Parameters
    ----------
    confluence_url, confluence_username, confluence_api_token:
        Confluence credentials. Falls back to env vars.
    jira_url, jira_username, jira_api_token:
        Jira credentials. Falls back to env vars.
    include_tools:
        Allowlist of MCP tool names to expose. ``None`` = all.
    exclude_tools:
        Denylist of MCP tool names to hide. ``None`` = none.
    read_only:
        If ``True``, set ``READ_ONLY_MODE=true`` so only read operations are
        available regardless of ``include_tools``.
    timeout_seconds:
        Read timeout for the MCP stdio connection.
    """
    env = _build_env(
        confluence_url=confluence_url,
        confluence_username=confluence_username,
        confluence_api_token=confluence_api_token,
        jira_url=jira_url,
        jira_username=jira_username,
        jira_api_token=jira_api_token,
        read_only=read_only,
    )

    if not env:
        raise ValueError(
            "No Atlassian credentials configured. "
            "Set CONFLUENCE_URL/CONFLUENCE_USERNAME/CONFLUENCE_API_TOKEN env vars "
            "or pass them explicitly."
        )

    logger.info(
        "Creating mcp-atlassian MCPTools (include=%s, exclude=%s, read_only=%s)",
        include_tools,
        exclude_tools,
        read_only,
    )

    # ── Determine which tools need user confirmation ──────────────────
    # Write/mutating tools require human approval before execution.
    # The Agno MCPTools `requires_confirmation_tools` parameter pauses
    # the agent run so the caller can confirm() or reject() each call.
    #
    # When include_tools is None we let the MCP server decide which
    # tools to expose.  We still pass the full write list as the
    # confirmation set — Agno will only apply it to tools that actually
    # appear in the server's toolkit, so non-existent names are ignored.
    confirmation_tools: List[str] = []
    if not read_only:
        if include_tools is not None:
            included_set = set(include_tools)
            confirmation_tools = [t for t in ATLASSIAN_WRITE_TOOLS if t in included_set]
        else:
            # Let Agno intersect with whatever the server exposes
            confirmation_tools = list(ATLASSIAN_WRITE_TOOLS)

    return MCPTools(
        command="uvx mcp-atlassian",
        env=env,
        transport="stdio",
        include_tools=include_tools,
        exclude_tools=exclude_tools,
        requires_confirmation_tools=confirmation_tools,
        timeout_seconds=timeout_seconds,
    )


def create_confluence_mcp_tools(
    *,
    confluence_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_token: Optional[str] = None,
    include_tools: Optional[List[str]] = None,
    read_only: bool = False,
    timeout_seconds: int = 30,
) -> MCPTools:
    """Convenience: create MCP tools scoped to Confluence operations.

    Defaults to ``CONFLUENCE_READ_TOOLS`` unless *include_tools* is given.
    Set *read_only=True* for server-enforced read-only mode.
    """
    return create_mcp_atlassian_tools(
        confluence_url=confluence_url,
        confluence_username=confluence_username,
        confluence_api_token=confluence_api_token,
        include_tools=include_tools or CONFLUENCE_READ_TOOLS,
        read_only=read_only,
        timeout_seconds=timeout_seconds,
    )


def create_confluence_all_mcp_tools(
    *,
    confluence_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_token: Optional[str] = None,
    read_only: bool = False,
    timeout_seconds: int = 30,
) -> MCPTools:
    """Create MCP tools with **all** Confluence tools (read + write)."""
    return create_mcp_atlassian_tools(
        confluence_url=confluence_url,
        confluence_username=confluence_username,
        confluence_api_token=confluence_api_token,
        include_tools=CONFLUENCE_ALL_TOOLS,
        read_only=read_only,
        timeout_seconds=timeout_seconds,
    )


def create_jira_mcp_tools(
    *,
    jira_url: Optional[str] = None,
    jira_username: Optional[str] = None,
    jira_api_token: Optional[str] = None,
    include_tools: Optional[List[str]] = None,
    read_only: bool = False,
    timeout_seconds: int = 30,
) -> MCPTools:
    """Convenience: create MCP tools scoped to Jira operations.

    Defaults to ``JIRA_READ_TOOLS`` unless *include_tools* is given.
    """
    return create_mcp_atlassian_tools(
        jira_url=jira_url,
        jira_username=jira_username,
        jira_api_token=jira_api_token,
        include_tools=include_tools or JIRA_READ_TOOLS,
        read_only=read_only,
        timeout_seconds=timeout_seconds,
    )


def create_jira_all_mcp_tools(
    *,
    jira_url: Optional[str] = None,
    jira_username: Optional[str] = None,
    jira_api_token: Optional[str] = None,
    read_only: bool = False,
    timeout_seconds: int = 30,
) -> MCPTools:
    """Create MCP tools with **all** Jira tools (read + write)."""
    return create_mcp_atlassian_tools(
        jira_url=jira_url,
        jira_username=jira_username,
        jira_api_token=jira_api_token,
        include_tools=JIRA_ALL_TOOLS,
        read_only=read_only,
        timeout_seconds=timeout_seconds,
    )


def create_atlassian_mcp_tools_auto(
    *,
    confluence_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_token: Optional[str] = None,
    jira_url: Optional[str] = None,
    jira_username: Optional[str] = None,
    jira_api_token: Optional[str] = None,
    include_tools: Optional[List[str]] = None,
    read_only: bool = False,
    timeout_seconds: int = 30,
) -> MCPTools:
    """Create MCP tools auto-detecting which services are available.

    When ``include_tools`` is ``None`` (default), the MCP server decides which
    tools to expose based on its own configuration (``TOOLSETS``, available
    credentials, etc.).  This avoids mismatches where the client requests
    tools the server cannot provide.

    Pass ``include_tools`` explicitly to restrict to a known subset, or
    ``read_only=True`` to restrict to read operations server-side.
    """
    return create_mcp_atlassian_tools(
        confluence_url=confluence_url,
        confluence_username=confluence_username,
        confluence_api_token=confluence_api_token,
        jira_url=jira_url,
        jira_username=jira_username,
        jira_api_token=jira_api_token,
        include_tools=include_tools,
        read_only=read_only,
        timeout_seconds=timeout_seconds,
    )


def create_atlassian_mcp_tools_readonly(
    *,
    confluence_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_token: Optional[str] = None,
    jira_url: Optional[str] = None,
    jira_username: Optional[str] = None,
    jira_api_token: Optional[str] = None,
    timeout_seconds: int = 30,
) -> MCPTools:
    """Create MCP tools with read-only mode enforced server-side.

    Sets ``READ_ONLY_MODE=true`` so the MCP server only exposes read
    operations regardless of which tools are available.
    """
    return create_mcp_atlassian_tools(
        confluence_url=confluence_url,
        confluence_username=confluence_username,
        confluence_api_token=confluence_api_token,
        jira_url=jira_url,
        jira_username=jira_username,
        jira_api_token=jira_api_token,
        read_only=True,
        timeout_seconds=timeout_seconds,
    )
