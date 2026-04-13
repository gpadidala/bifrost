"""Tests for datasource MCP tools."""

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
        service_accounts=ServiceAccounts(
            viewer="glsa_test_viewer",
            editor="glsa_test_editor",
        ),
    )
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    s.environments = {"dev": env}
    s.active_environment = "dev"
    s.active_role = "viewer"
    pool = ClientPool(s)
    _state.init(s, pool)


class TestListDatasources:
    @respx.mock
    async def test_returns_datasource_list(self) -> None:
        from grafana_mcp.tools.datasources import list_datasources

        respx.get("http://localhost:3000/api/datasources").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"uid": "prom-1", "name": "Prometheus", "type": "prometheus", "isDefault": True},
                    {"uid": "loki-1", "name": "Loki", "type": "loki", "isDefault": False},
                ],
            )
        )
        result = await list_datasources()
        assert len(result) == 2
        assert result[0].uid == "prom-1"
        assert result[0].is_default is True

    @respx.mock
    async def test_empty_list(self) -> None:
        from grafana_mcp.tools.datasources import list_datasources

        respx.get("http://localhost:3000/api/datasources").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await list_datasources()
        assert result == []


class TestQueryDatasource:
    @respx.mock
    async def test_returns_query_result(self) -> None:
        from grafana_mcp.tools.datasources import query_datasource

        respx.post("http://localhost:3000/api/ds/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": {
                        "A": {
                            "frames": [{"schema": {}, "data": {"values": [[1, 2, 3]]}}],
                            "status": 200,
                        }
                    }
                },
            )
        )
        result = await query_datasource(datasource_uid="prom-1", expr="up")
        assert result.frames_count == 1
        assert "A" in result.results
