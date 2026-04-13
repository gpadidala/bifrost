"""Tests for ClientPool."""

from __future__ import annotations

import pytest

from grafana_mcp.client.pool import ClientPool
from grafana_mcp.settings import EnvironmentConfig, ServiceAccounts, Settings


@pytest.fixture()
def settings_with_dev() -> Settings:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    s.environments = {
        "dev": EnvironmentConfig(
            base_url="http://localhost:3000",
            tls_verify=False,
            service_accounts=ServiceAccounts(viewer="glsa_viewer", editor="glsa_editor"),
        )
    }
    return s


class TestClientPool:
    async def test_get_returns_client(self, settings_with_dev: Settings) -> None:
        pool = ClientPool(settings_with_dev)
        client = await pool.get("dev", "viewer")
        assert client is not None
        await pool.close_all()

    async def test_get_caches_client(self, settings_with_dev: Settings) -> None:
        pool = ClientPool(settings_with_dev)
        c1 = await pool.get("dev", "viewer")
        c2 = await pool.get("dev", "viewer")
        assert c1 is c2
        await pool.close_all()

    async def test_different_roles_get_different_clients(self, settings_with_dev: Settings) -> None:
        pool = ClientPool(settings_with_dev)
        viewer_client = await pool.get("dev", "viewer")
        editor_client = await pool.get("dev", "editor")
        assert viewer_client is not editor_client
        await pool.close_all()

    async def test_unknown_env_raises(self, settings_with_dev: Settings) -> None:
        pool = ClientPool(settings_with_dev)
        with pytest.raises(ValueError, match="Unknown environment"):
            await pool.get("prod", "viewer")

    async def test_close_all_empties_pool(self, settings_with_dev: Settings) -> None:
        pool = ClientPool(settings_with_dev)
        await pool.get("dev", "viewer")
        assert len(pool._clients) == 1
        await pool.close_all()
        assert len(pool._clients) == 0
