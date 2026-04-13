"""Dashboard MCP tools — list, get, search, get_panels."""

from __future__ import annotations

from typing import Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.dashboard import DashboardDetail, DashboardPanel, DashboardSummary

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
