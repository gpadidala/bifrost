"""Tests for utility MCP tools (health_check, get_server_info)."""

from __future__ import annotations

import httpx
import pytest
import respx

from grafana_mcp import _state
from grafana_mcp.client.pool import ClientPool
from grafana_mcp.settings import EnvironmentConfig, ServiceAccounts, Settings

import grafana_mcp.tools  # noqa: F401


@pytest.fixture(autouse=True)
def setup_state() -> None:
    env = EnvironmentConfig(
        base_url="http://localhost:3000",
        tls_verify=False,
        timeout_seconds=5,
        rate_limit_rps=100,
        service_accounts=ServiceAccounts(viewer="glsa_test_viewer"),
    )
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    s.environments = {"dev": env}
    s.active_environment = "dev"
    s.active_role = "viewer"
    pool = ClientPool(s)
    _state.init(s, pool)


class TestHealthCheck:
    @respx.mock
    async def test_returns_health(self) -> None:
        from grafana_mcp.tools.utility import health_check

        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(
                200, json={"database": "ok", "version": "11.4.0", "commit": "abc123"}
            )
        )
        result = await health_check()
        assert result.database == "ok"
        assert result.version == "11.4.0"
        assert result.enterprise is False

    @respx.mock
    async def test_grafana_error_propagates(self) -> None:
        from grafana_mcp.tools.utility import health_check

        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(503, json={"message": "Service unavailable"})
        )
        from grafana_mcp.client.grafana import GrafanaError

        with pytest.raises(GrafanaError) as exc_info:
            await health_check()
        assert exc_info.value.status_code == 503


class TestGetServerInfo:
    @respx.mock
    async def test_returns_server_info(self) -> None:
        from grafana_mcp.tools.utility import get_server_info

        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(200, json={"database": "ok", "version": "11.4.0"})
        )
        result = await get_server_info()
        assert result.bifrost_version == "1.3.0"
        assert result.grafana_version == "11.4.0"
        assert result.active_environment == "dev"
        assert result.active_role == "viewer"

    @respx.mock
    async def test_grafana_failure_still_returns_info(self) -> None:
        from grafana_mcp.tools.utility import get_server_info

        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(503, json={"message": "down"})
        )
        # get_server_info swallows Grafana errors — should still return
        result = await get_server_info()
        assert result.bifrost_version == "1.3.0"
        assert result.grafana_version == ""  # empty because health call failed
