"""Alert MCP tools — list rules, get rule, list instances, silence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.alert import AlertInstance, AlertRule, SilenceResult

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]


@mcp.tool()
async def list_alert_rules(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[AlertRule]:
    """List all unified alerting rules.

    Args:
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``AlertRule`` objects with uid, title, group, and state config.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_alert_rules", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_alert_rules()
    return [AlertRule.from_api(r) for r in raw]


@mcp.tool()
async def get_alert_rule(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> AlertRule:
    """Get a single alert rule by UID.

    Args:
        uid:          Alert rule UID.
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        ``AlertRule`` with full rule metadata.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("get_alert_rule", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_alert_rule(uid)
    return AlertRule.from_api(raw)


@mcp.tool()
async def list_alert_instances(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[AlertInstance]:
    """List currently active alert instances (firing / pending / resolved).

    Args:
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``AlertInstance`` objects with fingerprint, status, labels, and timestamps.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_alert_instances", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_alert_instances()
    return [AlertInstance.from_api(a) for a in raw]


@mcp.tool()
async def silence_alert(
    matchers: list[dict[str, str]],
    duration_minutes: int = 60,
    comment: str = "Silenced via Bifröst MCP",
    created_by: str = "bifrost-mcp",
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> SilenceResult:
    """Create a Grafana alertmanager silence.

    Requires **editor** role or higher.

    Args:
        matchers:         List of label matchers, each a dict with keys
                          ``name``, ``value``, and optionally ``isRegex`` (bool as str).
                          Example: ``[{"name": "alertname", "value": "HighCPU", "isRegex": "false"}]``
        duration_minutes: How long the silence lasts in minutes (default 60).
        comment:          Human-readable reason for the silence.
        created_by:       Identity string recorded in Grafana (default ``"bifrost-mcp"``).
        environment:      Override the active environment.
        role:             Override the active role.

    Returns:
        ``SilenceResult`` with the new silence UUID and confirmation message.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("silence_alert", active_role)  # requires editor+

    now = datetime.now(tz=timezone.utc)
    ends_at = now.replace(second=0, microsecond=0)
    from datetime import timedelta

    ends_at = ends_at + timedelta(minutes=duration_minutes)

    body = {
        "matchers": [
            {
                "name": m["name"],
                "value": m["value"],
                "isRegex": str(m.get("isRegex", "false")).lower() == "true",
                "isEqual": True,
            }
            for m in matchers
        ],
        "startsAt": now.isoformat(),
        "endsAt": ends_at.isoformat(),
        "comment": comment,
        "createdBy": created_by,
    }

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    result = await client.create_silence(body)
    silence_id = result.get("silenceID", result.get("id", ""))
    return SilenceResult(silence_id=silence_id)
