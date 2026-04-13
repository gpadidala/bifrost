"""Folder MCP tools — list_folders."""

from __future__ import annotations

from typing import Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.folder import Folder

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]


@mcp.tool()
async def list_folders(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[Folder]:
    """List all Grafana folders (dashboard containers).

    Args:
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``Folder`` objects with uid, title, url, and parent_uid.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_folders", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_folders()
    return [Folder.from_api(f) for f in raw]
