"""Tests for BifrostClient SDK."""

from __future__ import annotations

import os

import httpx
import pytest
import respx

from grafana_mcp_sdk import BifrostClient


@pytest.fixture()
def client() -> BifrostClient:
    return BifrostClient(
        grafana_url="http://localhost:3000",
        token="glsa_test_token",
        tls_verify=False,
        timeout=5.0,
    )


class TestFromEnv:
    def test_raises_when_url_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GRAFANA_URL", raising=False)
        monkeypatch.setenv("GRAFANA_TOKEN", "glsa_test")
        with pytest.raises(EnvironmentError, match="GRAFANA_URL"):
            BifrostClient.from_env()

    def test_raises_when_token_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GRAFANA_URL", "http://localhost:3000")
        monkeypatch.delenv("GRAFANA_TOKEN", raising=False)
        with pytest.raises(EnvironmentError, match="GRAFANA_TOKEN"):
            BifrostClient.from_env()

    def test_creates_client_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GRAFANA_URL", "http://localhost:3000")
        monkeypatch.setenv("GRAFANA_TOKEN", "glsa_test")
        c = BifrostClient.from_env()
        assert c is not None


class TestGetHealth:
    @respx.mock
    async def test_returns_health(self, client: BifrostClient) -> None:
        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(200, json={"database": "ok", "version": "11.4.0"})
        )
        result = await client.get_health()
        assert result["database"] == "ok"

    @respx.mock
    async def test_raises_on_error(self, client: BifrostClient) -> None:
        respx.get("http://localhost:3000/api/health").mock(
            return_value=httpx.Response(503, json={"message": "down"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_health()


class TestListDashboards:
    @respx.mock
    async def test_returns_list(self, client: BifrostClient) -> None:
        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(
                200,
                json=[{"uid": "abc", "title": "CPU", "type": "dash-db"}],
            )
        )
        result = await client.list_dashboards()
        assert len(result) == 1
        assert result[0]["uid"] == "abc"

    @respx.mock
    async def test_empty_result(self, client: BifrostClient) -> None:
        respx.get("http://localhost:3000/api/search").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await client.list_dashboards()
        assert result == []


class TestListFolders:
    @respx.mock
    async def test_returns_folders(self, client: BifrostClient) -> None:
        respx.get("http://localhost:3000/api/folders").mock(
            return_value=httpx.Response(
                200, json=[{"uid": "f1", "title": "Infra", "url": "/dashboards/f/f1"}]
            )
        )
        result = await client.list_folders()
        assert len(result) == 1
        assert result[0]["uid"] == "f1"


class TestContextManager:
    async def test_async_context_manager(self) -> None:
        async with BifrostClient("http://localhost:3000", "glsa_test") as c:
            assert c is not None
        # No exception on exit = close() called successfully
