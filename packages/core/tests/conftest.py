"""Shared pytest fixtures for packages/core tests."""

from __future__ import annotations

import pytest

from grafana_mcp.settings import EnvironmentConfig, ServiceAccounts, Settings


@pytest.fixture()
def dev_env() -> EnvironmentConfig:
    """A minimal dev EnvironmentConfig pointing at localhost:3000."""
    return EnvironmentConfig(
        base_url="http://localhost:3000",
        tls_verify=False,
        timeout_seconds=5,
        rate_limit_rps=100,
        service_accounts=ServiceAccounts(
            viewer="glsa_test_viewer_xxxxxxxxxxxxxxxx",
            editor="glsa_test_editor_xxxxxxxxxxxxxxxx",
            admin="glsa_test_admin_xxxxxxxxxxxxxxxx",
        ),
    )


@pytest.fixture()
def settings(dev_env: EnvironmentConfig) -> Settings:
    """A Settings instance with a single dev environment, no real .env loaded."""
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
    )
    s.environments = {"dev": dev_env}
    s.active_environment = "dev"
    s.active_role = "viewer"
    return s
