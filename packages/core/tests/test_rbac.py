"""Tests for grafana_mcp.rbac."""

from __future__ import annotations

import pytest

from grafana_mcp.rbac import (
    TOOL_MINIMUM_ROLE,
    enforce_role,
    has_permission,
)


class TestHasPermission:
    def test_viewer_can_viewer(self) -> None:
        assert has_permission("viewer", "viewer") is True

    def test_viewer_cannot_editor(self) -> None:
        assert has_permission("viewer", "editor") is False

    def test_viewer_cannot_admin(self) -> None:
        assert has_permission("viewer", "admin") is False

    def test_editor_can_viewer(self) -> None:
        assert has_permission("editor", "viewer") is True

    def test_editor_can_editor(self) -> None:
        assert has_permission("editor", "editor") is True

    def test_editor_cannot_admin(self) -> None:
        assert has_permission("editor", "admin") is False

    def test_admin_can_all(self) -> None:
        for required in ("viewer", "editor", "admin"):
            assert has_permission("admin", required) is True  # type: ignore[arg-type]


class TestEnforceRole:
    async def test_viewer_allowed_for_viewer_tool(self) -> None:
        await enforce_role("list_dashboards", "viewer")  # should not raise

    async def test_viewer_blocked_for_editor_tool(self) -> None:
        with pytest.raises(PermissionError, match="silence_alert"):
            await enforce_role("silence_alert", "viewer")

    async def test_viewer_blocked_for_admin_tool(self) -> None:
        with pytest.raises(PermissionError, match="list_users"):
            await enforce_role("list_users", "viewer")

    async def test_editor_allowed_for_editor_tool(self) -> None:
        await enforce_role("silence_alert", "editor")  # should not raise

    async def test_admin_allowed_for_admin_tool(self) -> None:
        await enforce_role("list_users", "admin")  # should not raise

    async def test_unknown_tool_defaults_to_viewer(self) -> None:
        await enforce_role("nonexistent_tool", "viewer")  # should not raise


class TestToolMinimumRole:
    def test_all_tools_have_valid_roles(self) -> None:
        valid = {"viewer", "editor", "admin"}
        for tool, role in TOOL_MINIMUM_ROLE.items():
            assert role in valid, f"Tool '{tool}' has invalid role '{role}'"

    def test_silence_alert_requires_editor(self) -> None:
        assert TOOL_MINIMUM_ROLE["silence_alert"] == "editor"

    def test_list_users_requires_admin(self) -> None:
        assert TOOL_MINIMUM_ROLE["list_users"] == "admin"

    def test_health_check_requires_viewer(self) -> None:
        assert TOOL_MINIMUM_ROLE["health_check"] == "viewer"
