"""Tests for alert MCP tools."""

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
    s.active_role = "editor"  # editor to allow silence tests
    pool = ClientPool(s)
    _state.init(s, pool)


class TestListAlertRules:
    @respx.mock
    async def test_returns_alert_rules(self) -> None:
        from grafana_mcp.tools.alerts import list_alert_rules

        respx.get("http://localhost:3000/api/v1/provisioning/alert-rules").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uid": "rule-1",
                        "title": "High CPU",
                        "ruleGroup": "infra",
                        "noDataState": "NoData",
                        "execErrState": "Error",
                    }
                ],
            )
        )
        result = await list_alert_rules()
        assert len(result) == 1
        assert result[0].uid == "rule-1"
        assert result[0].title == "High CPU"

    @respx.mock
    async def test_empty_list(self) -> None:
        from grafana_mcp.tools.alerts import list_alert_rules

        respx.get("http://localhost:3000/api/v1/provisioning/alert-rules").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await list_alert_rules()
        assert result == []


class TestSilenceAlert:
    @respx.mock
    async def test_creates_silence(self) -> None:
        from grafana_mcp.tools.alerts import silence_alert

        respx.post(
            "http://localhost:3000/api/alertmanager/grafana/api/v2/silences"
        ).mock(
            return_value=httpx.Response(200, json={"silenceID": "silence-uuid-123"})
        )
        result = await silence_alert(
            matchers=[{"name": "alertname", "value": "HighCPU"}],
            duration_minutes=30,
            comment="Test silence",
        )
        assert result.silence_id == "silence-uuid-123"

    async def test_viewer_cannot_silence(self) -> None:
        from grafana_mcp.tools.alerts import silence_alert

        with pytest.raises(PermissionError, match="silence_alert"):
            await silence_alert(
                matchers=[{"name": "alertname", "value": "HighCPU"}],
                role="viewer",
            )
