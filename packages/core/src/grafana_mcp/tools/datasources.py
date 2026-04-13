"""Datasource MCP tools — list, get, query, test."""

from __future__ import annotations

from typing import Any, Literal

from .._app import mcp
from .._state import get_pool, get_settings
from ..rbac import enforce_role
from ..schemas.datasource import DatasourceDetail, DatasourceSummary, QueryResult, TestResult

GrafanaRole = Literal["viewer", "editor", "admin"]
GrafanaEnvironment = Literal["dev", "perf", "prod"]


@mcp.tool()
async def list_datasources(
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> list[DatasourceSummary]:
    """List all configured Grafana datasources.

    Args:
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        List of ``DatasourceSummary`` objects (uid, name, type, default flag).
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_datasources", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_datasources()
    return [DatasourceSummary.from_api(ds) for ds in raw]


@mcp.tool()
async def get_datasource(
    uid: str,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> DatasourceDetail:
    """Get full details for a datasource by its UID.

    Args:
        uid:          Datasource UID.
        environment:  Override the active environment.
        role:         Override the active role.

    Returns:
        ``DatasourceDetail`` with access mode, database, and read-only flag.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("get_datasource", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)
    raw = await client.get_datasource(uid)
    return DatasourceDetail.from_api(raw)


@mcp.tool()
async def query_datasource(
    datasource_uid: str,
    expr: str,
    ref_id: str = "A",
    time_from: str = "now-1h",
    time_to: str = "now",
    max_data_points: int = 500,
    environment: GrafanaEnvironment | None = None,
    role: GrafanaRole | None = None,
) -> QueryResult:
    """Run a query against a Grafana datasource.

    Supports any datasource type (Prometheus PromQL, Loki LogQL, SQL, etc.).
    The ``expr`` field should contain the query expression appropriate for the
    datasource type.

    Args:
        datasource_uid:  UID of the datasource to query.
        expr:            Query expression (PromQL, LogQL, SQL, etc.).
        ref_id:          Result reference ID for correlation (default ``"A"``).
        time_from:       Start of the time range (default ``"now-1h"``).
        time_to:         End of the time range (default ``"now"``).
        max_data_points: Maximum data points per series (default 500).
        environment:     Override the active environment.
        role:            Override the active role.

    Returns:
        ``QueryResult`` with raw results dict and frame count.
    """
    settings = get_settings()
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("query_datasource", active_role)

    pool = get_pool()
    client = await pool.get(env_name, active_role)

    queries: list[dict[str, Any]] = [
        {
            "refId": ref_id,
            "expr": expr,
            "datasource": {"uid": datasource_uid},
            "maxDataPoints": max_data_points,
        }
    ]
    raw = await client.query_datasource(
        uid=datasource_uid,
        queries=queries,
        time_from=time_from,
        time_to=time_to,
    )

    results = raw.get("results", {})
    frames_count = sum(
        len(r.get("frames", [])) for r in results.values() if isinstance(r, dict)
    )
    return QueryResult(results=results, frames_count=frames_count)
