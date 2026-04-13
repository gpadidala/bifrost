"""BifrostClient — high-level async Python client for Grafana via the Bifröst MCP API.

This client talks directly to the Grafana HTTP API (not via MCP protocol).
It is intended for use in scripts, notebooks, and CI pipelines where a
full MCP server round-trip is unnecessary.

Usage::

    from grafana_mcp_sdk import BifrostClient

    async with BifrostClient.from_env() as client:
        dashboards = await client.list_dashboards()
        for d in dashboards:
            print(d["title"])
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class BifrostClient:
    """Async Grafana HTTP client for direct API access.

    Args:
        grafana_url: Base URL of the Grafana instance (e.g. ``http://localhost:3000``).
        token:       Service-account token (``glsa_...``).
        tls_verify:  Whether to verify TLS certificates (default ``True``).
        timeout:     Request timeout in seconds (default ``30``).
    """

    def __init__(
        self,
        grafana_url: str,
        token: str,
        *,
        tls_verify: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=grafana_url.rstrip("/"),
            timeout=timeout,
            verify=tls_verify,
            http2=True,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    # ── Factory constructors ─────────────────────────────────────────────────

    @classmethod
    def from_env(
        cls,
        *,
        url_var: str = "GRAFANA_URL",
        token_var: str = "GRAFANA_TOKEN",
    ) -> BifrostClient:
        """Create a ``BifrostClient`` from environment variables.

        Args:
            url_var:   Env var name for the Grafana URL (default ``GRAFANA_URL``).
            token_var: Env var name for the service-account token (default ``GRAFANA_TOKEN``).

        Raises:
            EnvironmentError: If either env var is not set.
        """
        url = os.environ.get(url_var)
        token = os.environ.get(token_var)
        if not url:
            raise EnvironmentError(f"Environment variable {url_var!r} is not set.")
        if not token:
            raise EnvironmentError(f"Environment variable {token_var!r} is not set.")
        tls_verify = os.environ.get("GRAFANA_TLS_VERIFY", "true").lower() != "false"
        timeout = float(os.environ.get("GRAFANA_TIMEOUT", "30"))
        return cls(url, token, tls_verify=tls_verify, timeout=timeout)

    # ── Internal request helper ──────────────────────────────────────────────

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self._client.get(
            path,
            params={k: v for k, v in (params or {}).items() if v is not None},
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        response = await self._client.post(path, json=body)
        response.raise_for_status()
        return response.json() if response.content else {}

    # ── Health ───────────────────────────────────────────────────────────────

    async def get_health(self) -> dict[str, Any]:
        """GET /api/health — returns Grafana health dict."""
        return await self._get("/api/health")

    # ── Dashboards ───────────────────────────────────────────────────────────

    async def list_dashboards(
        self,
        query: str = "",
        tags: list[str] | None = None,
        folder_uid: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search for dashboards matching *query* and optional tag/folder filters.

        Returns:
            List of dashboard search-result dicts from the Grafana API.
        """
        params: dict[str, Any] = {"type": "dash-db", "limit": limit}
        if query:
            params["query"] = query
        if tags:
            params["tag"] = tags
        if folder_uid:
            params["folderUIDs"] = folder_uid
        result = await self._get("/api/search", params)
        return result if isinstance(result, list) else []

    async def get_dashboard(self, uid: str) -> dict[str, Any]:
        """GET /api/dashboards/uid/{uid} — full dashboard JSON."""
        return await self._get(f"/api/dashboards/uid/{uid}")

    # ── Datasources ─────────────────────────────────────────────────────────

    async def list_datasources(self) -> list[dict[str, Any]]:
        """GET /api/datasources — list all datasources."""
        result = await self._get("/api/datasources")
        return result if isinstance(result, list) else []

    async def query_datasource(
        self,
        datasource_uid: str,
        expr: str,
        time_from: str = "now-1h",
        time_to: str = "now",
        ref_id: str = "A",
    ) -> dict[str, Any]:
        """Run a query against *datasource_uid*.

        Args:
            datasource_uid: Target datasource UID.
            expr:           Query expression (PromQL, LogQL, SQL, etc.).
            time_from:      Start of the time range (default ``"now-1h"``).
            time_to:        End of the time range (default ``"now"``).
            ref_id:         Result reference ID (default ``"A"``).

        Returns:
            Raw results dict from the Grafana query API.
        """
        body = {
            "queries": [
                {
                    "refId": ref_id,
                    "expr": expr,
                    "datasource": {"uid": datasource_uid},
                }
            ],
            "from": time_from,
            "to": time_to,
        }
        return await self._post("/api/ds/query", body)

    # ── Alerts ───────────────────────────────────────────────────────────────

    async def list_alert_rules(self) -> list[dict[str, Any]]:
        """GET /api/v1/provisioning/alert-rules — list all alert rules."""
        result = await self._get("/api/v1/provisioning/alert-rules")
        return result if isinstance(result, list) else []

    async def list_alert_instances(self) -> list[dict[str, Any]]:
        """GET /api/v1/alerts — list active alert instances."""
        result = await self._get("/api/v1/alerts")
        return result if isinstance(result, list) else []

    # ── Folders ─────────────────────────────────────────────────────────────

    async def list_folders(self) -> list[dict[str, Any]]:
        """GET /api/folders — list all folders."""
        result = await self._get("/api/folders")
        return result if isinstance(result, list) else []

    # ── Context-manager support ─────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    async def __aenter__(self) -> BifrostClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
