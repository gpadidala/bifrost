"""Async Grafana HTTP client with retry, rate limiting, and token injection."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

from ..settings import EnvironmentConfig, GrafanaRole
from .retry import grafana_retry

logger = structlog.get_logger(__name__)


class GrafanaError(Exception):
    """Raised when the Grafana API returns a non-2xx response after retries."""

    def __init__(self, status_code: int, message: str, path: str) -> None:
        self.status_code = status_code
        self.path = path
        super().__init__(f"Grafana API error {status_code} on {path}: {message}")


class GrafanaClient:
    """Typed async Grafana HTTP client.

    One instance per (environment, role) pair.  Create via ``ClientPool`` rather
    than directly so that instances are reused across tool calls.

    Args:
        env:  The ``EnvironmentConfig`` describing the Grafana instance.
        role: The active role — determines which service-account token is used.
    """

    def __init__(self, env: EnvironmentConfig, role: GrafanaRole) -> None:
        self.env = env
        self.role = role

        token = env.service_accounts.token_for(role).get_secret_value()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.AsyncClient(
            base_url=env.base_url.rstrip("/"),
            timeout=float(env.timeout_seconds),
            verify=env.tls_verify,
            http2=True,
            headers=headers,
        )
        # Simple token-bucket rate limiting via asyncio.Semaphore.
        # The semaphore limits concurrent in-flight requests; combined with the
        # retry back-off this provides effective rate control.
        self._semaphore = asyncio.Semaphore(max(1, env.rate_limit_rps))
        self._log = logger.bind(role=role, base_url=env.base_url)

    # ── Low-level request helpers ────────────────────────────────────────────

    @grafana_retry
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an HTTP request and return the parsed JSON body.

        Raises:
            GrafanaError: On non-2xx responses after all retry attempts.
        """
        async with self._semaphore:
            t0 = time.monotonic()
            response = await self._client.request(
                method,
                path,
                params={k: v for k, v in (params or {}).items() if v is not None},
                json=json,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

        self._log.debug(
            "grafana_request",
            method=method,
            path=path,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )

        if response.is_error:
            try:
                detail = response.json().get("message", response.text)
            except Exception:
                detail = response.text
            raise GrafanaError(response.status_code, detail, path)

        if response.content:
            return response.json()
        return {}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """HTTP GET — returns parsed JSON."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, body: dict[str, Any]) -> Any:
        """HTTP POST with JSON body — returns parsed JSON."""
        return await self._request("POST", path, json=body)

    async def put(self, path: str, body: dict[str, Any]) -> Any:
        """HTTP PUT with JSON body — returns parsed JSON."""
        return await self._request("PUT", path, json=body)

    async def delete(self, path: str) -> Any:
        """HTTP DELETE — returns parsed JSON."""
        return await self._request("DELETE", path)

    # ── Grafana-specific API methods ────────────────────────────────────────

    async def get_health(self) -> dict[str, Any]:
        """GET /api/health — Grafana health check."""
        return await self.get("/api/health")

    async def get_version(self) -> dict[str, Any]:
        """GET /api/frontend/settings — extracts build info for version."""
        return await self.get("/api/frontend/settings")

    async def search_dashboards(
        self,
        query: str = "",
        tags: list[str] | None = None,
        folder_uid: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """GET /api/search — search dashboards."""
        params: dict[str, Any] = {
            "type": "dash-db",
            "limit": limit,
        }
        if query:
            params["query"] = query
        if tags:
            params["tag"] = tags
        if folder_uid:
            params["folderUIDs"] = folder_uid
        result = await self.get("/api/search", params=params)
        return result if isinstance(result, list) else []

    async def get_dashboard(self, uid: str) -> dict[str, Any]:
        """GET /api/dashboards/uid/{uid}."""
        return await self.get(f"/api/dashboards/uid/{uid}")

    async def get_datasources(self) -> list[dict[str, Any]]:
        """GET /api/datasources — list all datasources."""
        result = await self.get("/api/datasources")
        return result if isinstance(result, list) else []

    async def get_datasource(self, uid: str) -> dict[str, Any]:
        """GET /api/datasources/uid/{uid}."""
        return await self.get(f"/api/datasources/uid/{uid}")

    async def test_datasource(self, uid: str) -> dict[str, Any]:
        """POST /api/datasources/uid/{uid}/health — test datasource connectivity."""
        return await self.get(f"/api/datasources/uid/{uid}/health")

    async def query_datasource(
        self,
        uid: str,
        queries: list[dict[str, Any]],
        time_from: str = "now-1h",
        time_to: str = "now",
    ) -> dict[str, Any]:
        """POST /api/ds/query — run a query against a datasource."""
        body = {
            "queries": queries,
            "from": time_from,
            "to": time_to,
        }
        return await self.post("/api/ds/query", body)

    async def get_alert_rules(self) -> list[dict[str, Any]]:
        """GET /api/v1/provisioning/alert-rules — list unified alert rules."""
        result = await self.get("/api/v1/provisioning/alert-rules")
        return result if isinstance(result, list) else []

    async def get_alert_rule(self, uid: str) -> dict[str, Any]:
        """GET /api/v1/provisioning/alert-rules/{uid}."""
        return await self.get(f"/api/v1/provisioning/alert-rules/{uid}")

    async def get_alert_instances(self) -> list[dict[str, Any]]:
        """GET /api/v1/alerts — list active alert instances."""
        result = await self.get("/api/v1/alerts")
        return result if isinstance(result, list) else []

    async def create_silence(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /api/alertmanager/grafana/api/v2/silences — create a silence."""
        return await self.post(
            "/api/alertmanager/grafana/api/v2/silences", body
        )

    async def get_folders(self) -> list[dict[str, Any]]:
        """GET /api/folders — list all folders."""
        result = await self.get("/api/folders")
        return result if isinstance(result, list) else []

    async def get_users(self) -> list[dict[str, Any]]:
        """GET /api/org/users — list org users (admin)."""
        result = await self.get("/api/org/users")
        return result if isinstance(result, list) else []

    async def get_service_accounts(self) -> list[dict[str, Any]]:
        """GET /api/serviceaccounts/search — list service accounts (admin)."""
        result = await self.get("/api/serviceaccounts/search")
        if isinstance(result, dict):
            return result.get("serviceAccounts", [])
        return []

    async def close(self) -> None:
        """Close the underlying httpx client and release connections."""
        await self._client.aclose()

    # ── Context-manager support ─────────────────────────────────────────────

    async def __aenter__(self) -> GrafanaClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
