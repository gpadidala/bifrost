"""Dashboard-related Pydantic output schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    """Minimal dashboard descriptor returned by search and list operations."""

    uid: str = Field(description="Grafana dashboard UID.")
    title: str = Field(description="Dashboard display title.")
    url: str = Field(default="", description="Relative URL path — append to Grafana base URL.")
    folder_title: str = Field(default="", alias="folderTitle", description="Parent folder name.")
    folder_uid: str = Field(default="", alias="folderUid", description="Parent folder UID.")
    tags: list[str] = Field(default_factory=list, description="Dashboard tags.")
    type: str = Field(default="dash-db", description="Item type — always 'dash-db' for dashboards.")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_search_result(cls, raw: dict[str, Any]) -> DashboardSummary:
        """Construct from a raw Grafana /api/search result item."""
        return cls(
            uid=raw.get("uid", ""),
            title=raw.get("title", ""),
            url=raw.get("url", ""),
            folder_title=raw.get("folderTitle", ""),
            folder_uid=raw.get("folderUid", ""),
            tags=raw.get("tags", []),
            type=raw.get("type", "dash-db"),
        )


class DashboardPanel(BaseModel):
    """A single panel within a Grafana dashboard."""

    id: int = Field(description="Panel numeric ID (unique within dashboard).")
    title: str = Field(default="", description="Panel title.")
    type: str = Field(default="", description="Panel type — e.g. 'graph', 'stat', 'table'.")
    datasource: str = Field(default="", description="Datasource UID or name used by this panel.")
    description: str = Field(default="", description="Panel description / help text.")


class DashboardDetail(BaseModel):
    """Full dashboard descriptor including panels and metadata."""

    uid: str = Field(description="Grafana dashboard UID.")
    title: str = Field(description="Dashboard display title.")
    version: int = Field(default=0, description="Dashboard schema version.")
    tags: list[str] = Field(default_factory=list, description="Dashboard tags.")
    panels: list[DashboardPanel] = Field(
        default_factory=list,
        description="List of panels in the dashboard.",
    )
    folder_uid: str = Field(default="", description="Parent folder UID.")
    folder_title: str = Field(default="", description="Parent folder title.")
    url: str = Field(default="", description="Relative URL — append to Grafana base URL.")

    @classmethod
    def from_api_response(cls, raw: dict[str, Any]) -> DashboardDetail:
        """Construct from the raw ``GET /api/dashboards/uid/{uid}`` response."""
        meta = raw.get("meta", {})
        dashboard = raw.get("dashboard", {})

        raw_panels = dashboard.get("panels", [])
        panels = []
        for p in raw_panels:
            ds = p.get("datasource") or {}
            if isinstance(ds, str):
                ds_uid = ds
            else:
                ds_uid = ds.get("uid", "")
            panels.append(
                DashboardPanel(
                    id=p.get("id", 0),
                    title=p.get("title", ""),
                    type=p.get("type", ""),
                    datasource=ds_uid,
                    description=p.get("description", ""),
                )
            )

        return cls(
            uid=dashboard.get("uid", ""),
            title=dashboard.get("title", ""),
            version=dashboard.get("version", 0),
            tags=dashboard.get("tags", []),
            panels=panels,
            folder_uid=meta.get("folderUid", ""),
            folder_title=meta.get("folderTitle", ""),
            url=meta.get("url", ""),
        )


class DashboardMutationResult(BaseModel):
    """Result of a create/update/delete dashboard operation."""

    ok: bool = Field(default=True, description="Whether the operation succeeded.")
    uid: str = Field(default="", description="Dashboard UID (empty for delete).")
    url: str = Field(default="", description="Relative dashboard URL.")
    version: int = Field(default=0, description="New dashboard version.")
    status: str = Field(default="success", description="Grafana status string.")
    message: str = Field(default="", description="Human-readable result message.")
