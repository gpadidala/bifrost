"""Tests for dashboard MCP tools."""

from __future__ import annotations

import httpx
import pytest
import respx

from grafana_mcp import _state
from grafana_mcp.client.pool import ClientPool
from grafana_mcp.settings import EnvironmentConfig, ServiceAccounts, Settings

# Ensure tools are registered
import grafana_mcp.tools  # noqa: F401


@pytest.fixture(autouse=True)
def setup_state() -> None:
    """Inject a real Settings + ClientPool into _state before each test."""
    env = EnvironmentConfig(
        base_url="http://localhost:3000",
        tls_verify=False,
        timeout_seconds=5,
        rate_limit_rps=100,
        service_accounts=ServiceAccounts(
            viewer="glsa_test_viewer",
            editor="glsa_test_editor",
            admin="glsa_test_admin",
        ),
    )
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    s.environments = {"dev": env}
    s.active_environment = "dev"
    s.active_role = "viewer"
    pool = ClientPool(s)
    _state.init(s, pool)


class TestListDashboards:
    @respx.mock
    async def test_returns_dashboard_summaries(self) -> None:
        from grafana_mcp.tools.dashboards import list_dashboards

        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uid": "abc",
                        "title": "CPU Overview",
                        "type": "dash-db",
                        "folderTitle": "Infra",
                        "tags": ["cpu", "infra"],
                    }
                ],
            )
        )
        result = await list_dashboards()
        assert len(result) == 1
        assert result[0].uid == "abc"
        assert result[0].title == "CPU Overview"

    @respx.mock
    async def test_empty_result(self) -> None:
        from grafana_mcp.tools.dashboards import list_dashboards

        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await list_dashboards()
        assert result == []

    async def test_role_rejection(self) -> None:
        from grafana_mcp.tools.dashboards import list_dashboards

        # list_dashboards requires viewer — even admin-less callers are fine;
        # test that an editor-only tool rejects viewer
        from grafana_mcp.tools.alerts import silence_alert

        with pytest.raises(PermissionError):
            await silence_alert(
                matchers=[{"name": "alertname", "value": "Test"}],
                role="viewer",
            )


class TestGetDashboard:
    @respx.mock
    async def test_returns_dashboard_detail(self) -> None:
        from grafana_mcp.tools.dashboards import get_dashboard

        respx.get("http://localhost:3000/api/dashboards/uid/abc123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "dashboard": {
                        "uid": "abc123",
                        "title": "My Dashboard",
                        "version": 5,
                        "tags": ["prod"],
                        "panels": [
                            {"id": 1, "title": "CPU", "type": "graph", "datasource": {"uid": "prom"}}
                        ],
                    },
                    "meta": {"folderUid": "f1", "folderTitle": "Infra", "url": "/d/abc123"},
                },
            )
        )
        result = await get_dashboard("abc123")
        assert result.uid == "abc123"
        assert result.title == "My Dashboard"
        assert len(result.panels) == 1
        assert result.panels[0].title == "CPU"


class TestSearchDashboards:
    @respx.mock
    async def test_search_with_query(self) -> None:
        from grafana_mcp.tools.dashboards import search_dashboards

        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(
                200,
                json=[{"uid": "xyz", "title": "CPU Usage", "type": "dash-db"}],
            )
        )
        result = await search_dashboards(query="CPU")
        assert len(result) == 1
        assert result[0].title == "CPU Usage"
