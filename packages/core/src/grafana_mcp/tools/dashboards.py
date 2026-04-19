"""Dashboard MCP tools — list, get, search, get_panels."""

from __future__ import annotations

from typing import Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.dashboard import (
    DashboardDetail,
    DashboardMutationResult,
    DashboardPanel,
    DashboardSummary,
)

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]


@mcp.tool()
async def list_dashboards(
    folder_uid: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[DashboardSummary]:
    """List dashboards, optionally filtered by folder UID and tags.

    Args:
        folder_uid:   Filter to a specific Grafana folder (by UID).
        tags:         Filter by one or more dashboard tags.
        limit:        Maximum number of results to return (default 100).
        environment:  Override the active environment (dev | perf | prod).
        role:         Override the active role (viewer | editor | admin).

    Returns:
        List of ``DashboardSummary`` objects with uid, title, folder, and tags.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_dashboards", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.search_dashboards(
        folder_uid=folder_uid,
        tags=tags,
        limit=limit,
    )
    return [DashboardSummary.from_search_result(item) for item in raw]


@mcp.tool()
async def search_dashboards(
    query: str,
    tags: list[str] | None = None,
    limit: int = 50,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[DashboardSummary]:
    """Full-text search for dashboards by title.

    Args:
        query:        Search string matched against dashboard titles.
        tags:         Optional tag filters applied alongside the text query.
        limit:        Maximum number of results (default 50).
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``DashboardSummary`` objects matching the query.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("search_dashboards", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.search_dashboards(query=query, tags=tags, limit=limit)
    return [DashboardSummary.from_search_result(item) for item in raw]


@mcp.tool()
async def get_dashboard(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardDetail:
    """Retrieve a complete dashboard by its UID, including all panels.

    Args:
        uid:          Dashboard UID (e.g. ``"abc123XYZ"``).
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        ``DashboardDetail`` with metadata and a list of ``DashboardPanel`` objects.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("get_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_dashboard(uid)
    return DashboardDetail.from_api_response(raw)


@mcp.tool()
async def get_dashboard_panels(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[DashboardPanel]:
    """List all panels in a specific dashboard.

    Args:
        uid:          Dashboard UID.
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``DashboardPanel`` objects (id, title, type, datasource).
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("get_dashboard_panels", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_dashboard(uid)
    detail = DashboardDetail.from_api_response(raw)
    return detail.panels


@mcp.tool()
async def create_dashboard(
    title: str,
    tags: list[str] | None = None,
    folder_uid: str | None = None,
    panels: list[dict] | None = None,
    description: str = "",
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardMutationResult:
    """Create a new dashboard in Grafana.

    Args:
        title:        Dashboard title (required).
        tags:         Tags to attach (e.g. ["kpi", "payment-service"]).
        folder_uid:   Target folder UID; omit for the General folder.
        panels:       Optional list of panel dicts (Grafana panel JSON).
                      If empty, an empty dashboard is created.
        description:  Dashboard description shown in the UI.
        environment:  Override the active environment.
        role:         Override the active role. Minimum: editor.

    Returns:
        ``DashboardMutationResult`` with the new UID, URL, and version.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("create_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)

    dashboard_body: dict = {
        "uid": None,  # let Grafana generate
        "title": title,
        "tags": tags or [],
        "timezone": "browser",
        "schemaVersion": 38,
        "version": 0,
        "refresh": "30s",
        "panels": panels or [],
    }
    if description:
        dashboard_body["description"] = description

    body: dict = {
        "dashboard": dashboard_body,
        "overwrite": False,
        "message": f"Created via O11yBot MCP",
    }
    if folder_uid:
        body["folderUid"] = folder_uid

    raw = await client.post("/api/dashboards/db", body)
    return DashboardMutationResult(
        ok=True,
        uid=raw.get("uid", ""),
        url=raw.get("url", ""),
        version=raw.get("version", 0),
        status=raw.get("status", "success"),
        message=f"Dashboard '{title}' created",
    )


@mcp.tool()
async def update_dashboard(
    uid: str,
    title: str | None = None,
    tags: list[str] | None = None,
    panels: list[dict] | None = None,
    description: str | None = None,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardMutationResult:
    """Update an existing dashboard in-place.

    Only fields explicitly provided are changed; everything else
    is preserved from the current dashboard JSON.

    Args:
        uid:          UID of the dashboard to update (required).
        title:        New title (optional).
        tags:         New tag list (optional — replaces existing).
        panels:       New panel list (optional — replaces existing).
        description:  New description (optional).
        environment:  Override the active environment.
        role:         Override the active role. Minimum: editor.

    Returns:
        ``DashboardMutationResult`` with the updated UID, URL, and bumped version.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("update_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)

    raw = await client.get_dashboard(uid)
    dashboard = raw.get("dashboard", {})
    if title is not None:
        dashboard["title"] = title
    if tags is not None:
        dashboard["tags"] = tags
    if panels is not None:
        dashboard["panels"] = panels
    if description is not None:
        dashboard["description"] = description

    body = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": "Updated via O11yBot MCP",
    }
    meta = raw.get("meta", {})
    if meta.get("folderUid"):
        body["folderUid"] = meta["folderUid"]

    resp = await client.post("/api/dashboards/db", body)
    return DashboardMutationResult(
        ok=True,
        uid=resp.get("uid", uid),
        url=resp.get("url", ""),
        version=resp.get("version", 0),
        status=resp.get("status", "success"),
        message=f"Dashboard {uid} updated",
    )


@mcp.tool()
async def delete_dashboard(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardMutationResult:
    """Delete a dashboard by UID.

    Args:
        uid:          UID of the dashboard to delete.
        environment:  Override the active environment.
        role:         Override the active role. Minimum: admin.

    Returns:
        ``DashboardMutationResult`` with status='deleted'.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("delete_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    await client.delete(f"/api/dashboards/uid/{uid}")
    return DashboardMutationResult(
        ok=True,
        uid=uid,
        status="deleted",
        message=f"Dashboard {uid} deleted",
    )
