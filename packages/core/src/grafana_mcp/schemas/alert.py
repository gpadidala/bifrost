"""Alert-related Pydantic output schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AlertRule(BaseModel):
    """Unified alerting rule summary."""

    uid: str = Field(description="Alert rule UID.")
    title: str = Field(description="Alert rule title.")
    namespace_uid: str = Field(default="", description="Folder/namespace UID the rule belongs to.")
    rule_group: str = Field(default="", description="Alert rule group name.")
    condition: str = Field(default="", description="Condition expression reference (e.g. 'C').")
    no_data_state: str = Field(default="NoData", description="Behaviour when no data — NoData | Alerting | OK.")
    exec_err_state: str = Field(default="Error", description="Behaviour on execution error — Error | Alerting | OK.")

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> AlertRule:
        """Construct from a raw provisioning API alert rule."""
        return cls(
            uid=raw.get("uid", ""),
            title=raw.get("title", ""),
            namespace_uid=raw.get("folderUID", ""),
            rule_group=raw.get("ruleGroup", ""),
            condition=raw.get("condition", ""),
            no_data_state=raw.get("noDataState", "NoData"),
            exec_err_state=raw.get("execErrState", "Error"),
        )


class AlertInstance(BaseModel):
    """A single active alert instance from the alertmanager."""

    fingerprint: str = Field(description="Unique alert fingerprint.")
    status: str = Field(default="", description="Alert state — 'firing', 'resolved', etc.")
    labels: dict[str, str] = Field(default_factory=dict, description="Alert labels.")
    annotations: dict[str, str] = Field(default_factory=dict, description="Alert annotations.")
    starts_at: str = Field(default="", description="ISO-8601 timestamp when the alert started firing.")
    ends_at: str = Field(default="", description="ISO-8601 timestamp when the alert resolved (empty if still firing).")

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> AlertInstance:
        status_info = raw.get("status", {})
        if isinstance(status_info, dict):
            state = status_info.get("state", "")
        else:
            state = str(status_info)
        return cls(
            fingerprint=raw.get("fingerprint", ""),
            status=state,
            labels=raw.get("labels", {}),
            annotations=raw.get("annotations", {}),
            starts_at=raw.get("startsAt", ""),
            ends_at=raw.get("endsAt", ""),
        )


class Silence(BaseModel):
    """An existing Grafana alertmanager silence."""

    id: str = Field(description="Silence UUID.")
    status: str = Field(default="", description="Silence state — 'active', 'expired', 'pending'.")
    comment: str = Field(default="", description="Human-readable reason for the silence.")
    created_by: str = Field(default="", description="Creator identity.")
    starts_at: str = Field(default="", description="ISO-8601 start timestamp.")
    ends_at: str = Field(default="", description="ISO-8601 end timestamp.")
    matchers: list[dict[str, str]] = Field(
        default_factory=list, description="Label matchers applied by this silence."
    )


class SilenceResult(BaseModel):
    """Result of creating a silence via ``silence_alert``."""

    silence_id: str = Field(description="UUID of the newly created silence.")
    message: str = Field(default="Silence created.", description="Human-readable confirmation.")
