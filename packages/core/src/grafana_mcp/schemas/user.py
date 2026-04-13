"""User and service-account Pydantic output schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserSummary(BaseModel):
    """An org user summary returned by ``list_users``."""

    user_id: int = Field(description="Grafana user ID.")
    login: str = Field(description="Login / username.")
    name: str = Field(default="", description="Display name.")
    email: str = Field(default="", description="User email address.")
    role: str = Field(default="Viewer", description="Org role — Viewer | Editor | Admin.")
    is_disabled: bool = Field(default=False, description="True if the account is disabled.")

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> UserSummary:
        return cls(
            user_id=raw.get("userId", 0),
            login=raw.get("login", ""),
            name=raw.get("name", ""),
            email=raw.get("email", ""),
            role=raw.get("role", "Viewer"),
            is_disabled=raw.get("isDisabled", False),
        )


class ServiceAccount(BaseModel):
    """A Grafana service account returned by ``list_service_accounts``."""

    id: int = Field(description="Service account numeric ID.")
    name: str = Field(description="Service account name.")
    login: str = Field(default="", description="Login identifier.")
    role: str = Field(default="Viewer", description="Org role assigned to this service account.")
    is_disabled: bool = Field(default=False, description="True if the service account is disabled.")
    tokens_count: int = Field(default=0, description="Number of API tokens associated with this account.")

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> ServiceAccount:
        return cls(
            id=raw.get("id", 0),
            name=raw.get("name", ""),
            login=raw.get("login", ""),
            role=raw.get("role", "Viewer"),
            is_disabled=raw.get("isDisabled", False),
            tokens_count=raw.get("tokensCount", 0),
        )
