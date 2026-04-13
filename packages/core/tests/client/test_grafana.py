"""Tests for GrafanaClient using respx-mocked HTTP."""

from __future__ import annotations

import httpx
import pytest
import respx

from grafana_mcp.client.grafana import GrafanaClient, GrafanaError
from grafana_mcp.settings import EnvironmentConfig, ServiceAccounts


@pytest.fixture()
def dev_env() -> EnvironmentConfig:
    return EnvironmentConfig(
        base_url="http://localhost:3000",
        tls_verify=False,
        timeout_seconds=5,
        rate_limit_rps=100,
        service_accounts=ServiceAccounts(viewer="glsa_test_viewer"),
    )


@pytest.fixture()
def client(dev_env: EnvironmentConfig) -> GrafanaClient:
    return GrafanaClient(dev_env, role="viewer")


class TestGetHealth:
    @respx.mock
    async def test_returns_health_dict(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(200, json={"database": "ok", "version": "11.4.0"})
        )
        result = await client.get_health()
        assert result["database"] == "ok"
        assert result["version"] == "11.4.0"

    @respx.mock
    async def test_raises_grafana_error_on_500(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(500, json={"message": "internal error"})
        )
        with pytest.raises(GrafanaError) as exc_info:
            await client.get_health()
        assert exc_info.value.status_code == 500


class TestSearchDashboards:
    @respx.mock
    async def test_returns_list(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(
                200,
                json=[{"uid": "abc", "title": "My Dashboard", "type": "dash-db"}],
            )
        )
        result = await client.search_dashboards()
        assert len(result) == 1
        assert result[0]["uid"] == "abc"

    @respx.mock
    async def test_empty_list_on_no_results(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await client.search_dashboards()
        assert result == []

    @respx.mock
    async def test_raises_on_401(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(401, json={"message": "Unauthorized"})
        )
        with pytest.raises(GrafanaError) as exc_info:
            await client.search_dashboards()
        assert exc_info.value.status_code == 401


class TestGetDashboard:
    @respx.mock
    async def test_returns_dashboard(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/dashboards/uid/abc123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "dashboard": {"uid": "abc123", "title": "Test", "panels": []},
                    "meta": {"folderUid": "", "folderTitle": "", "url": "/d/abc123"},
                },
            )
        )
        result = await client.get_dashboard("abc123")
        assert result["dashboard"]["uid"] == "abc123"


class TestGetDatasources:
    @respx.mock
    async def test_returns_datasource_list(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/datasources").mock(
            return_value=httpx.Response(
                200,
                json=[{"uid": "prom-uid", "name": "Prometheus", "type": "prometheus"}],
            )
        )
        result = await client.get_datasources()
        assert len(result) == 1
        assert result[0]["type"] == "prometheus"


class TestGetAlertRules:
    @respx.mock
    async def test_returns_empty_list_on_204(self, client: GrafanaClient) -> None:
        respx.get("http://localhost:3000/api/v1/provisioning/alert-rules").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await client.get_alert_rules()
        assert result == []


class TestClose:
    async def test_close_does_not_raise(self, dev_env: EnvironmentConfig) -> None:
        c = GrafanaClient(dev_env, role="viewer")
        await c.close()  # should not raise


class TestGrafanaError:
    def test_str_representation(self) -> None:
        err = GrafanaError(404, "Not found", "/api/dashboards/uid/missing")
        assert "404" in str(err)
        assert "Not found" in str(err)
