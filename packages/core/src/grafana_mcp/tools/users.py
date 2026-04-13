"""User and service-account MCP tools — list_users, list_service_accounts (admin only)."""

from __future__ import annotations

from typing import Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.user import ServiceAccount, UserSummary

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]


@mcp.tool()
async def list_users(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[UserSummary]:
    """List all users in the Grafana organisation.

    Requires **admin** role.

    Args:
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``UserSummary`` objects with login, name, email, and org role.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_users", active_role)  # admin required

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_users()
    return [UserSummary.from_api(u) for u in raw]


@mcp.tool()
async def list_service_accounts(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[ServiceAccount]:
    """List all Grafana service accounts.

    Requires **admin** role.

    Args:
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``ServiceAccount`` objects with id, name, role, and token count.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_service_accounts", active_role)  # admin required

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_service_accounts()
    return [ServiceAccount.from_api(sa) for sa in raw]
