"""Pydantic Settings for Bifröst — 12-factor configuration via environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]


class ServiceAccounts(BaseSettings):
    """Per-role service-account tokens for a single Grafana environment."""

    model_config = SettingsConfigDict(populate_by_name=True)

    viewer: SecretStr = SecretStr("")
    editor: SecretStr = SecretStr("")
    admin: SecretStr = SecretStr("")

    def token_for(self, role: GrafanaRole) -> SecretStr:
        """Return the token for the given role."""
        return getattr(self, role)

    def has_token(self, role: GrafanaRole) -> bool:
        """Return True if a non-empty token is configured for *role*."""
        return bool(self.token_for(role).get_secret_value())


class EnvironmentConfig(BaseSettings):
    """Configuration for a single Grafana environment (dev / perf / prod)."""

    model_config = SettingsConfigDict(populate_by_name=True)

    base_url: str = "http://localhost:3000"
    tls_verify: bool = True
    timeout_seconds: int = 30
    rate_limit_rps: int = 10
    service_accounts: ServiceAccounts = ServiceAccounts()


class TransportConfig(BaseSettings):
    """MCP transport configuration."""

    model_config = SettingsConfigDict(populate_by_name=True)

    mode: Literal["sse", "http", "stdio"] = "sse"
    host: str = "0.0.0.0"
    port: int = 8765
    path_prefix: str = "/mcp"


class Settings(BaseSettings):
    """Root settings — every field maps to a ``GRAFANA_MCP_*`` environment variable.

    Nested delimiter is ``__`` so::

        GRAFANA_MCP_ENVIRONMENTS__DEV__BASE_URL=http://localhost:3000

    maps to ``settings.environments["dev"].base_url``.
    """

    model_config = SettingsConfigDict(
        env_prefix="GRAFANA_MCP_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    active_environment: GrafanaEnvironment = "dev"
    active_role: GrafanaRole = "viewer"
    transport: TransportConfig = TransportConfig()
    environments: dict[str, EnvironmentConfig] = {}
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    @field_validator("log_level", mode="before")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def normalize_and_default_environments(self) -> Settings:
        """Lowercase environment keys; inject a minimal dev fallback if missing."""
        self.environments = {k.lower(): v for k, v in self.environments.items()}
        if not self.environments:
            self.environments = {
                "dev": EnvironmentConfig(base_url="http://localhost:3000", tls_verify=False),
                "perf": EnvironmentConfig(base_url="https://grafana-perf.example.com"),
                "prod": EnvironmentConfig(base_url="https://grafana.example.com"),
            }
        return self

    def get_environment(self, name: str | None = None) -> EnvironmentConfig:
        """Return the ``EnvironmentConfig`` for *name* (defaults to active_environment)."""
        env_name = (name or self.active_environment).lower()
        try:
            return self.environments[env_name]
        except KeyError as exc:
            available = ", ".join(self.environments)
            raise ValueError(
                f"Unknown environment {env_name!r}. Available: {available}"
            ) from exc
