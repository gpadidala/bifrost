"""Dashboard MCP tools — list, get, search, get_panels."""

from __future__ import annotations

from typing import Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.dashboard import (
    DashboardDetail,
    DashboardMutationResult,
    DashboardPanel,
    DashboardSummary,
)

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]


@mcp.tool()
async def list_dashboards(
    folder_uid: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[DashboardSummary]:
    """List dashboards, optionally filtered by folder UID and tags.

    Args:
        folder_uid:   Filter to a specific Grafana folder (by UID).
        tags:         Filter by one or more dashboard tags.
        limit:        Maximum number of results to return (default 100).
        environment:  Override the active environment (dev | perf | prod).
        role:         Override the active role (viewer | editor | admin).

    Returns:
        List of ``DashboardSummary`` objects with uid, title, folder, and tags.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_dashboards", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.search_dashboards(
        folder_uid=folder_uid,
        tags=tags,
        limit=limit,
    )
    return [DashboardSummary.from_search_result(item) for item in raw]


@mcp.tool()
async def search_dashboards(
    query: str,
    tags: list[str] | None = None,
    limit: int = 50,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[DashboardSummary]:
    """Full-text search for dashboards by title.

    Args:
        query:        Search string matched against dashboard titles.
        tags:         Optional tag filters applied alongside the text query.
        limit:        Maximum number of results (default 50).
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``DashboardSummary`` objects matching the query.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("search_dashboards", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.search_dashboards(query=query, tags=tags, limit=limit)
    return [DashboardSummary.from_search_result(item) for item in raw]


@mcp.tool()
async def get_dashboard(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardDetail:
    """Retrieve a complete dashboard by its UID, including all panels.

    Args:
        uid:          Dashboard UID (e.g. ``"abc123XYZ"``).
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        ``DashboardDetail`` with metadata and a list of ``DashboardPanel`` objects.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("get_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_dashboard(uid)
    return DashboardDetail.from_api_response(raw)


@mcp.tool()
async def get_dashboard_panels(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[DashboardPanel]:
    """List all panels in a specific dashboard.

    Args:
        uid:          Dashboard UID.
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``DashboardPanel`` objects (id, title, type, datasource).
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("get_dashboard_panels", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_dashboard(uid)
    detail = DashboardDetail.from_api_response(raw)
    return detail.panels


@mcp.tool()
async def create_dashboard(
    title: str,
    tags: list[str] | None = None,
    folder_uid: str | None = None,
    panels: list[dict] | None = None,
    description: str = "",
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardMutationResult:
    """Create a new dashboard in Grafana.

    Args:
        title:        Dashboard title (required).
        tags:         Tags to attach (e.g. ["kpi", "payment-service"]).
        folder_uid:   Target folder UID; omit for the General folder.
        panels:       Optional list of panel dicts (Grafana panel JSON).
                      If empty, an empty dashboard is created.
        description:  Dashboard description shown in the UI.
        environment:  Override the active environment.
        role:         Override the active role. Minimum: editor.

    Returns:
        ``DashboardMutationResult`` with the new UID, URL, and version.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("create_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)

    dashboard_body: dict = {
        "uid": None,  # let Grafana generate
        "title": title,
        "tags": tags or [],
        "timezone": "browser",
        "schemaVersion": 38,
        "version": 0,
        "refresh": "30s",
        "panels": panels or [],
    }
    if description:
        dashboard_body["description"] = description

    body: dict = {
        "dashboard": dashboard_body,
        "overwrite": False,
        "message": f"Created via O11yBot MCP",
    }
    if folder_uid:
        body["folderUid"] = folder_uid

    raw = await client.post("/api/dashboards/db", body)
    return DashboardMutationResult(
        ok=True,
        uid=raw.get("uid", ""),
        url=raw.get("url", ""),
        version=raw.get("version", 0),
        status=raw.get("status", "success"),
        message=f"Dashboard '{title}' created",
    )


@mcp.tool()
async def update_dashboard(
    uid: str,
    title: str | None = None,
    tags: list[str] | None = None,
    panels: list[dict] | None = None,
    description: str | None = None,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardMutationResult:
    """Update an existing dashboard in-place.

    Only fields explicitly provided are changed; everything else
    is preserved from the current dashboard JSON.

    Args:
        uid:          UID of the dashboard to update (required).
        title:        New title (optional).
        tags:         New tag list (optional — replaces existing).
        panels:       New panel list (optional — replaces existing).
        description:  New description (optional).
        environment:  Override the active environment.
        role:         Override the active role. Minimum: editor.

    Returns:
        ``DashboardMutationResult`` with the updated UID, URL, and bumped version.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("update_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)

    raw = await client.get_dashboard(uid)
    dashboard = raw.get("dashboard", {})
    if title is not None:
        dashboard["title"] = title
    if tags is not None:
        dashboard["tags"] = tags
    if panels is not None:
        dashboard["panels"] = panels
    if description is not None:
        dashboard["description"] = description

    body = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": "Updated via O11yBot MCP",
    }
    meta = raw.get("meta", {})
    if meta.get("folderUid"):
        body["folderUid"] = meta["folderUid"]

    resp = await client.post("/api/dashboards/db", body)
    return DashboardMutationResult(
        ok=True,
        uid=resp.get("uid", uid),
        url=resp.get("url", ""),
        version=resp.get("version", 0),
        status=resp.get("status", "success"),
        message=f"Dashboard {uid} updated",
    )


@mcp.tool()
async def delete_dashboard(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardMutationResult:
    """Delete a dashboard by UID.

    Args:
        uid:          UID of the dashboard to delete.
        environment:  Override the active environment.
        role:         Override the active role. Minimum: admin.

    Returns:
        ``DashboardMutationResult`` with status='deleted'.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("delete_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    await client.delete(f"/api/dashboards/uid/{uid}")
    return DashboardMutationResult(
        ok=True,
        uid=uid,
        status="deleted",
        message=f"Dashboard {uid} deleted",
    )


# ═══════════════════════════════════════════════════════════════
# create_smart_dashboard — builds RED + resource panels from the
# default Prometheus datasource, all inside the MCP layer.
# ═══════════════════════════════════════════════════════════════


def _regex_for_topic(topic: str) -> str:
    """Build a PromQL label regex that matches the topic across naming styles.

    'payment-service' → '.*(payment|payment-service|payment_service).*'
    """
    t = topic.strip().lower()
    variants = {t, t.replace(" ", "-"), t.replace(" ", "_"), t.replace("-", "_"), t.replace("-", " ")}
    # Drop empties and the obvious stopwords
    variants = {v for v in variants if v and v not in {"the", "a", "an"}}
    parts = "|".join(sorted(variants, key=len, reverse=True))
    return f".*({parts}).*"


def _grid_pos(x: int, y: int, w: int = 12, h: int = 8) -> dict:
    return {"x": x, "y": y, "w": w, "h": h}


def _timeseries_panel(pid: int, title: str, ds_uid: str, expr: str, pos: dict, unit: str = "short", legend: str = "{{service}}") -> dict:
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "datasource": {"type": "prometheus", "uid": ds_uid},
        "gridPos": pos,
        "targets": [
            {"refId": "A", "expr": expr, "legendFormat": legend, "datasource": {"type": "prometheus", "uid": ds_uid}},
        ],
        "fieldConfig": {
            "defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 10}},
            "overrides": [],
        },
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
    }


def _stat_panel(pid: int, title: str, ds_uid: str, expr: str, pos: dict, unit: str = "short") -> dict:
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "datasource": {"type": "prometheus", "uid": ds_uid},
        "gridPos": pos,
        "targets": [
            {"refId": "A", "expr": expr, "datasource": {"type": "prometheus", "uid": ds_uid}, "legendFormat": ""},
        ],
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {"colorMode": "value", "graphMode": "area", "reduceOptions": {"values": False, "calcs": ["lastNotNull"]}},
    }


def _row_panel(pid: int, title: str, y: int) -> dict:
    return {
        "id": pid,
        "type": "row",
        "title": title,
        "collapsed": False,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": [],
    }


def _build_red_panels(topic: str, ds_uid: str) -> list[dict]:
    """Generate a RED + resource usage panel set for the given topic.

    Uses label regex so the dashboard instantly works against any service name
    containing the topic string — no metric discovery round-trip needed.
    """
    regex = _regex_for_topic(topic)
    panels: list[dict] = []
    pid = 1

    # Row: Request health (RED)
    panels.append(_row_panel(pid, f"{topic.title()} — Request Health (RED)", 0))
    pid += 1

    # Stat: requests/sec now
    panels.append(_stat_panel(
        pid, "Requests / sec (now)", ds_uid,
        f'sum(rate(http_requests_total{{service=~"{regex}"}}[5m]))',
        _grid_pos(0, 1, 6, 4), unit="reqps",
    ))
    pid += 1

    # Stat: error rate %
    panels.append(_stat_panel(
        pid, "Error rate % (5m)", ds_uid,
        f'100 * sum(rate(http_requests_total{{service=~"{regex}", status=~"5.."}}[5m])) / '
        f'clamp_min(sum(rate(http_requests_total{{service=~"{regex}"}}[5m])), 0.001)',
        _grid_pos(6, 1, 6, 4), unit="percent",
    ))
    pid += 1

    # Stat: p95 latency ms
    panels.append(_stat_panel(
        pid, "p95 latency (ms)", ds_uid,
        f'1000 * histogram_quantile(0.95, sum by (le) '
        f'(rate(http_request_duration_seconds_bucket{{service=~"{regex}"}}[5m])))',
        _grid_pos(12, 1, 6, 4), unit="ms",
    ))
    pid += 1

    # Stat: p99 latency ms
    panels.append(_stat_panel(
        pid, "p99 latency (ms)", ds_uid,
        f'1000 * histogram_quantile(0.99, sum by (le) '
        f'(rate(http_request_duration_seconds_bucket{{service=~"{regex}"}}[5m])))',
        _grid_pos(18, 1, 6, 4), unit="ms",
    ))
    pid += 1

    # Time series: request rate by service
    panels.append(_timeseries_panel(
        pid, "Request rate by service", ds_uid,
        f'sum by (service) (rate(http_requests_total{{service=~"{regex}"}}[5m]))',
        _grid_pos(0, 5, 12, 8), unit="reqps",
    ))
    pid += 1

    # Time series: error rate by service
    panels.append(_timeseries_panel(
        pid, "Error rate by service (5xx)", ds_uid,
        f'sum by (service) (rate(http_requests_total{{service=~"{regex}", status=~"5.."}}[5m]))',
        _grid_pos(12, 5, 12, 8), unit="reqps",
    ))
    pid += 1

    # Time series: latency quantiles
    panels.append(_timeseries_panel(
        pid, "Latency — p50 / p95 / p99",
        ds_uid,
        'label_replace(\n'
        f'  histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket{{service=~"{regex}"}}[5m]))),\n'
        '  "q", "p50", "instance", ".*"\n'
        ')',
        _grid_pos(0, 13, 24, 8), unit="s", legend="p50",
    ))
    pid += 1

    # Row: Resource usage
    panels.append(_row_panel(pid, f"{topic.title()} — Resource Usage", 21))
    pid += 1

    panels.append(_timeseries_panel(
        pid, "CPU usage by pod", ds_uid,
        f'sum by (pod) (rate(container_cpu_usage_seconds_total{{pod=~"{regex}"}}[5m]))',
        _grid_pos(0, 22, 12, 8), unit="short", legend="{{pod}}",
    ))
    pid += 1

    panels.append(_timeseries_panel(
        pid, "Memory usage by pod", ds_uid,
        f'sum by (pod) (container_memory_working_set_bytes{{pod=~"{regex}"}})',
        _grid_pos(12, 22, 12, 8), unit="bytes", legend="{{pod}}",
    ))
    pid += 1

    # Row: Logs + saturation hints
    panels.append(_row_panel(pid, f"{topic.title()} — Saturation", 30))
    pid += 1

    panels.append(_timeseries_panel(
        pid, "In-flight requests", ds_uid,
        f'sum by (service) (http_requests_in_flight{{service=~"{regex}"}})',
        _grid_pos(0, 31, 12, 8), unit="short",
    ))
    pid += 1

    panels.append(_timeseries_panel(
        pid, "Request size p95 (bytes)", ds_uid,
        f'histogram_quantile(0.95, sum by (le) (rate(http_request_size_bytes_bucket{{service=~"{regex}"}}[5m])))',
        _grid_pos(12, 31, 12, 8), unit="bytes",
    ))

    return panels


async def _default_prometheus_ds_uid(client) -> str:
    """Return the first Prometheus-typed datasource UID, or '' if none."""
    try:
        ds_list = await client.get_datasources()
        for d in ds_list:
            if d.get("type", "").lower() in ("prometheus", "grafanacloud-prometheus"):
                return d.get("uid") or ""
        # Fallback: any default datasource
        for d in ds_list:
            if d.get("isDefault"):
                return d.get("uid") or ""
    except Exception:
        pass
    return ""


@mcp.tool()
async def create_smart_dashboard(
    title: str,
    topic: str | None = None,
    tags: list[str] | None = None,
    folder_uid: str | None = None,
    datasource_uid: str | None = None,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DashboardMutationResult:
    """Create a dashboard pre-populated with RED + resource panels for a topic.

    Queries the default Prometheus datasource (unless ``datasource_uid`` is
    provided), builds panels with PromQL targets that filter by a label regex
    derived from ``topic``, and creates the dashboard in one MCP call — no
    orchestrator-side panel construction.

    Args:
        title:          Dashboard title (required).
        topic:          Topic / service name the panels should filter for.
                        Defaults to ``title`` lowercased.
        tags:           Extra tags to attach (topic is auto-added).
        folder_uid:     Target folder; omit for General.
        datasource_uid: Prometheus datasource UID. Auto-discovered if omitted.
        environment:    Override the active environment.
        role:           Override the active role. Minimum: editor.

    Returns:
        ``DashboardMutationResult`` with the new UID, URL, and version.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("create_smart_dashboard", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)

    ds_uid = datasource_uid or await _default_prometheus_ds_uid(client)
    if not ds_uid:
        return DashboardMutationResult(
            ok=False,
            status="no_datasource",
            message="No Prometheus datasource found. Pass datasource_uid explicitly.",
        )

    topic_str = (topic or title).strip().lower()
    panels = _build_red_panels(topic_str, ds_uid)
    all_tags = list({*(tags or []), topic_str.replace(" ", "-"), "o11ybot", "auto-generated"})

    body: dict = {
        "dashboard": {
            "uid": None,
            "title": title,
            "tags": all_tags,
            "timezone": "browser",
            "schemaVersion": 38,
            "version": 0,
            "refresh": "30s",
            "description": f"Auto-generated RED + resource dashboard for {topic_str}.",
            "panels": panels,
            "templating": {"list": []},
            "time": {"from": "now-1h", "to": "now"},
        },
        "overwrite": False,
        "message": f"Created via O11yBot (smart template for {topic_str})",
    }
    if folder_uid:
        body["folderUid"] = folder_uid

    raw = await client.post("/api/dashboards/db", body)
    return DashboardMutationResult(
        ok=True,
        uid=raw.get("uid", ""),
        url=raw.get("url", ""),
        version=raw.get("version", 0),
        status=raw.get("status", "success"),
        message=f"Smart dashboard '{title}' created with {len(panels)} panels (RED + resources) filtered for '{topic_str}'",
    )
