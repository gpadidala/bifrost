"""Folder-related Pydantic output schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Folder(BaseModel):
    """A Grafana folder (dashboard container)."""

    uid: str = Field(description="Folder UID.")
    title: str = Field(description="Folder display name.")
    url: str = Field(default="", description="Relative URL — append to Grafana base URL.")
    parent_uid: str = Field(default="", description="Parent folder UID (empty for root-level folders).")

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Folder:
        """Construct from a raw ``GET /api/folders`` list item."""
        return cls(
            uid=raw.get("uid", ""),
            title=raw.get("title", ""),
            url=raw.get("url", ""),
            parent_uid=raw.get("parentUid", ""),
        )
