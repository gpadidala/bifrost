"""Common output schemas shared across multiple tool groups."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GrafanaHealth(BaseModel):
    """Result of a Grafana health check."""

    database: str = Field(description="Database connectivity status — 'ok' or error message.")
    version: str = Field(default="", description="Grafana build version string.")
    commit: str = Field(default="", description="Git commit SHA of the Grafana build.")
    enterprise: bool = Field(default=False, description="True if this is a Grafana Enterprise instance.")


class ServerInfo(BaseModel):
    """Bifröst server metadata returned by ``get_server_info``."""

    bifrost_version: str = Field(description="Bifröst package version.")
    grafana_version: str = Field(default="", description="Grafana build version string.")
    active_environment: str = Field(description="Currently active Grafana environment key.")
    active_role: str = Field(description="Currently active role.")
    transport: str = Field(description="Active MCP transport mode (sse | http | stdio).")
