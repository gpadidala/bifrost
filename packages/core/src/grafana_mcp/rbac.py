"""Role-Based Access Control for Bifröst MCP tools.

Three roles in ascending privilege order:
    viewer  — read-only access (list/get, no mutations)
    editor  — can silence alerts, create annotations
    admin   — user management, service-account management

Every registered tool must appear in ``TOOL_MINIMUM_ROLE`` (or have a comment
saying it is intentionally unrestricted).
"""

from __future__ import annotations

from typing import Literal

GrafanaRole = Literal["viewer", "editor", "admin"]

#: Ordered list of roles from least to most privileged.
ROLE_HIERARCHY: list[GrafanaRole] = ["viewer", "editor", "admin"]

#: Maps each registered tool name to the minimum role required to call it.
#: Tools not in this dict are assumed to require "viewer" (read-only default).
TOOL_MINIMUM_ROLE: dict[str, GrafanaRole] = {
    # ── Dashboard tools (viewer) ─────────────────────────────────────
    "list_dashboards": "viewer",
    "get_dashboard": "viewer",
    "search_dashboards": "viewer",
    "get_dashboard_panels": "viewer",
    # ── Datasource tools ────────────────────────────────────────────
    "list_datasources": "viewer",
    "get_datasource": "viewer",
    "query_datasource": "viewer",
    # ── Alert tools ─────────────────────────────────────────────────
    "list_alert_rules": "viewer",
    "get_alert_rule": "viewer",
    "list_alert_instances": "viewer",
    "silence_alert": "editor",  # mutates Grafana state
    # ── Folder tools ────────────────────────────────────────────────
    "list_folders": "viewer",
    # ── User / service-account tools ─────────────────────────────────
    "list_users": "admin",
    "list_service_accounts": "admin",
    # ── Utility tools ───────────────────────────────────────────────
    "health_check": "viewer",
    "get_server_info": "viewer",
}


def _role_level(role: GrafanaRole) -> int:
    """Return the numeric privilege level for *role* (higher = more privileged)."""
    return ROLE_HIERARCHY.index(role)


def has_permission(caller_role: GrafanaRole, required_role: GrafanaRole) -> bool:
    """Return True when *caller_role* meets or exceeds *required_role*."""
    return _role_level(caller_role) >= _role_level(required_role)


async def enforce_role(tool_name: str, caller_role: GrafanaRole) -> None:
    """Raise ``PermissionError`` if *caller_role* is insufficient for *tool_name*.

    Args:
        tool_name:   The registered MCP tool name.
        caller_role: The role of the current MCP session.

    Raises:
        PermissionError: If the caller's role is below the minimum required.
    """
    required = TOOL_MINIMUM_ROLE.get(tool_name, "viewer")
    if not has_permission(caller_role, required):
        raise PermissionError(
            f"Tool '{tool_name}' requires role '{required}', "
            f"but caller has role '{caller_role}'."
        )
