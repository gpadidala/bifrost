"""Utility MCP tools — health_check, get_server_info."""

from __future__ import annotations

from typing import Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.common import GrafanaHealth, ServerInfo

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]

_BIFROST_VERSION = "1.3.0"


@mcp.tool()
async def health_check(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> GrafanaHealth:
    """Ping Grafana and return its health status.

    Calls ``GET /api/health`` on the target environment and returns the
    database status, Grafana version, and whether this is an Enterprise instance.

    Args:
        environment:  Override the active environment (default: active_environment).
        role:         Override the active role (default: active_role).

    Returns:
        ``GrafanaHealth`` with database status, version, and enterprise flag.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("health_check", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_health()

    return GrafanaHealth(
        database=raw.get("database", "unknown"),
        version=raw.get("version", ""),
        commit=raw.get("commit", ""),
        enterprise="enterprise" in raw.get("version", "").lower(),
    )


@mcp.tool()
async def get_server_info(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> ServerInfo:
    """Return Bifröst server metadata and the connected Grafana version.

    Args:
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        ``ServerInfo`` with Bifröst version, Grafana version, active env/role, and transport.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("get_server_info", active_role)

    grafana_version = ""
    try:
        pool = get_pool()
        client = await pool.get(env_name, active_role)
        health = await client.get_health()
        grafana_version = health.get("version", "")
    except Exception:  # noqa: BLE001 — best-effort, don't fail server info on Grafana errors
        pass

    return ServerInfo(
        bifrost_version=_BIFROST_VERSION,
        grafana_version=grafana_version,
        active_environment=env_name,
        active_role=active_role,
        transport=settings.transport.mode,
    )
