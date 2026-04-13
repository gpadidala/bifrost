"""Datasource-related Pydantic output schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DatasourceSummary(BaseModel):
    """Minimal datasource descriptor."""

    uid: str = Field(description="Datasource UID.")
    name: str = Field(description="Datasource display name.")
    type: str = Field(description="Plugin type — e.g. 'prometheus', 'loki', 'postgres'.")
    url: str = Field(default="", description="Connection URL for the datasource (may be empty for internal).")
    is_default: bool = Field(default=False, alias="isDefault", description="True if this is the org default datasource.")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> DatasourceSummary:
        """Construct from a raw datasource list item."""
        return cls(
            uid=raw.get("uid", raw.get("id", "")),
            name=raw.get("name", ""),
            type=raw.get("type", ""),
            url=raw.get("url", ""),
            is_default=raw.get("isDefault", False),
        )


class DatasourceDetail(DatasourceSummary):
    """Full datasource descriptor including access mode and JSON data."""

    access: str = Field(default="proxy", description="Access mode — 'proxy' or 'direct'.")
    database: str = Field(default="", description="Database name (for SQL datasources).")
    read_only: bool = Field(default=False, alias="readOnly", description="True if the datasource is configured as read-only.")

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> DatasourceDetail:  # type: ignore[override]
        """Construct from a raw single-datasource API response."""
        return cls(
            uid=raw.get("uid", str(raw.get("id", ""))),
            name=raw.get("name", ""),
            type=raw.get("type", ""),
            url=raw.get("url", ""),
            is_default=raw.get("isDefault", False),
            access=raw.get("access", "proxy"),
            database=raw.get("database", ""),
            read_only=raw.get("readOnly", False),
        )


class TestResult(BaseModel):
    """Result of datasource connectivity test."""

    status: str = Field(description="'OK' on success, error message otherwise.")
    message: str = Field(default="", description="Human-readable details from the datasource plugin.")


class QueryResult(BaseModel):
    """Result of a datasource query (``query_datasource``)."""

    results: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw query results keyed by refId. Schema varies by datasource type.",
    )
    frames_count: int = Field(
        default=0,
        description="Total number of data frames returned across all result sets.",
    )
