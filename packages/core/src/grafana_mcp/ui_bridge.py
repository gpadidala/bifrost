"""REST bridge for the browser UI.

The MCP SSE/stdio transports speak JSON-RPC, which is awkward to consume
from a ``fetch()`` call. This module exposes REST routes that internally
invoke the same tool functions (respecting the exact same role
enforcement, pooling, and retry logic) and return plain JSON.

In addition to read endpoints, the bridge supports **runtime
reconfiguration** of environments, active env/role selection, and
per-role connection tests. Edits are in-memory only and do not persist
across restarts — the UI is responsible for writing changes back to its
own localStorage or exporting them to `.env`.

Routes are mounted at ``/api/*`` alongside ``/healthz`` and ``/mcp/*``.

This is a convenience for the bundled React UI. It is NOT a stable
public contract — agents should use the MCP endpoints instead.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, SecretStr
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import _state
from ._app import mcp
from .client.grafana import GrafanaClient
from .rbac import TOOL_MINIMUM_ROLE
from .settings import EnvironmentConfig, ServiceAccounts
from .tools import alerts as _alerts
from .tools import dashboards as _dashboards
from .tools import datasources as _datasources
from .tools import folders as _folders
from .tools import users as _users
from .tools import utility as _utility

# Name → async function map. Mirrors @mcp.tool() registrations.
_TOOL_DISPATCH: dict[str, Any] = {
    "list_dashboards": _dashboards.list_dashboards,
    "search_dashboards": _dashboards.search_dashboards,
    "get_dashboard": _dashboards.get_dashboard,
    "get_dashboard_panels": _dashboards.get_dashboard_panels,
    "list_datasources": _datasources.list_datasources,
    "get_datasource": _datasources.get_datasource,
    "query_datasource": _datasources.query_datasource,
    "list_folders": _folders.list_folders,
    "list_alert_rules": _alerts.list_alert_rules,
    "get_alert_rule": _alerts.get_alert_rule,
    "list_alert_instances": _alerts.list_alert_instances,
    "silence_alert": _alerts.silence_alert,
    "list_users": _users.list_users,
    "list_service_accounts": _users.list_service_accounts,
    "health_check": _utility.health_check,
    "get_server_info": _utility.get_server_info,
}

_VALID_ENVS = ("dev", "perf", "prod")
_VALID_ROLES = ("viewer", "editor", "admin")


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(v) for v in value]
    if isinstance(value, dict):
        return {k: _dump(v) for k, v in value.items()}
    return value


def _ok(data: Any = None) -> JSONResponse:
    return JSONResponse({"ok": True, "data": _dump(data)})


def _err(error: str, message: str, status: int = 500) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error, "message": message}, status_code=status)


async def _call_tool(fn: Any, **kwargs: Any) -> JSONResponse:
    try:
        result = await fn(**kwargs)
        return _ok(result)
    except PermissionError as exc:
        return _err("PermissionError", str(exc), 403)
    except Exception as exc:  # noqa: BLE001
        return _err(exc.__class__.__name__, str(exc), 500)


# ── settings + environments ────────────────────────────────────────────────


def _describe_env(cfg: EnvironmentConfig) -> dict[str, Any]:
    return {
        "base_url": cfg.base_url,
        "tls_verify": cfg.tls_verify,
        "timeout_seconds": cfg.timeout_seconds,
        "rate_limit_rps": cfg.rate_limit_rps,
        "has_viewer": cfg.service_accounts.has_token("viewer"),
        "has_editor": cfg.service_accounts.has_token("editor"),
        "has_admin": cfg.service_accounts.has_token("admin"),
    }


async def server_info(request: Request) -> JSONResponse:
    settings = _state.get_settings()
    envs = {name: _describe_env(cfg) for name, cfg in settings.environments.items()}
    # Always surface all three named envs to the UI, even if unconfigured
    for name in _VALID_ENVS:
        envs.setdefault(
            name,
            {
                "base_url": "",
                "tls_verify": True,
                "timeout_seconds": 30,
                "rate_limit_rps": 10,
                "has_viewer": False,
                "has_editor": False,
                "has_admin": False,
            },
        )
    return _ok(
        {
            "version": "1.3.0",
            "active_environment": settings.active_environment,
            "active_role": settings.active_role,
            "transport": {
                "mode": settings.transport.mode,
                "host": settings.transport.host,
                "port": settings.transport.port,
                "path_prefix": settings.transport.path_prefix,
            },
            "environments": envs,
        }
    )


async def update_environment(request: Request) -> JSONResponse:
    name = request.path_params["name"].lower()
    if name not in _VALID_ENVS:
        return _err("ValueError", f"environment must be one of {_VALID_ENVS}", 400)
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        return _err("ValueError", f"invalid JSON body: {exc}", 400)

    settings = _state.get_settings()
    pool = _state.get_pool()

    existing = settings.environments.get(name)
    if existing is None:
        existing = EnvironmentConfig()
        settings.environments[name] = existing

    if "base_url" in body:
        existing.base_url = body["base_url"].rstrip("/")
    if "tls_verify" in body:
        existing.tls_verify = bool(body["tls_verify"])
    if "timeout_seconds" in body:
        existing.timeout_seconds = int(body["timeout_seconds"])
    if "rate_limit_rps" in body:
        existing.rate_limit_rps = int(body["rate_limit_rps"])

    tokens = body.get("service_accounts") or {}
    accounts = existing.service_accounts or ServiceAccounts()
    for role in _VALID_ROLES:
        if role in tokens:
            val = tokens[role] or ""
            setattr(accounts, role, SecretStr(val))
    existing.service_accounts = accounts

    # Evict cached clients for this env so next call rebuilds with new tokens/url
    evicted = 0
    for key in list(pool._clients.keys()):  # type: ignore[attr-defined]
        if key[0] == name:
            client = pool._clients.pop(key)  # type: ignore[attr-defined]
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass
            evicted += 1

    return _ok({"environment": name, "evicted": evicted, "config": _describe_env(existing)})


async def set_active(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        return _err("ValueError", f"invalid JSON body: {exc}", 400)

    settings = _state.get_settings()
    if "environment" in body:
        env = body["environment"].lower()
        if env not in _VALID_ENVS:
            return _err("ValueError", f"environment must be one of {_VALID_ENVS}", 400)
        if env not in settings.environments:
            return _err("ValueError", f"environment {env!r} is not configured", 400)
        settings.active_environment = env  # type: ignore[assignment]
    if "role" in body:
        role = body["role"].lower()
        if role not in _VALID_ROLES:
            return _err("ValueError", f"role must be one of {_VALID_ROLES}", 400)
        settings.active_role = role  # type: ignore[assignment]

    return _ok(
        {
            "active_environment": settings.active_environment,
            "active_role": settings.active_role,
        }
    )


async def test_environment(request: Request) -> JSONResponse:
    name = request.path_params["name"].lower()
    if name not in _VALID_ENVS:
        return _err("ValueError", f"environment must be one of {_VALID_ENVS}", 400)
    settings = _state.get_settings()
    env_cfg = settings.environments.get(name)
    if env_cfg is None:
        return _err("ValueError", f"environment {name!r} is not configured", 400)

    role_results: dict[str, Any] = {}
    for role in _VALID_ROLES:
        if not env_cfg.service_accounts.has_token(role):
            role_results[role] = {"status": "missing", "latency_ms": None, "error": None}
            continue
        client = GrafanaClient(env_cfg, role)
        t0 = time.monotonic()
        try:
            await client.get_health()
            role_results[role] = {
                "status": "ok",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            role_results[role] = {
                "status": "error",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "error": str(exc)[:200],
            }
        finally:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass

    return _ok({"environment": name, "base_url": env_cfg.base_url, "roles": role_results})


# ── tool proxies ───────────────────────────────────────────────────────────


async def list_dashboards(request: Request) -> JSONResponse:
    folder = request.query_params.get("folder_uid")
    tags = request.query_params.getlist("tag")
    try:
        limit = int(request.query_params.get("limit", "200"))
    except ValueError:
        limit = 200
    env = request.query_params.get("env")
    role = request.query_params.get("role")
    kwargs: dict[str, Any] = {"folder_uid": folder, "tags": tags or None, "limit": limit}
    if env:
        kwargs["environment"] = env
    if role:
        kwargs["role"] = role
    return await _call_tool(_dashboards.list_dashboards, **kwargs)


async def get_dashboard(request: Request) -> JSONResponse:
    uid = request.path_params["uid"]
    return await _call_tool(_dashboards.get_dashboard, uid=uid)


async def list_datasources(request: Request) -> JSONResponse:
    env = request.query_params.get("env")
    role = request.query_params.get("role")
    kwargs: dict[str, Any] = {}
    if env:
        kwargs["environment"] = env
    if role:
        kwargs["role"] = role
    return await _call_tool(_datasources.list_datasources, **kwargs)


async def list_folders(request: Request) -> JSONResponse:
    env = request.query_params.get("env")
    role = request.query_params.get("role")
    kwargs: dict[str, Any] = {}
    if env:
        kwargs["environment"] = env
    if role:
        kwargs["role"] = role
    return await _call_tool(_folders.list_folders, **kwargs)


async def health_check(request: Request) -> JSONResponse:
    return await _call_tool(_utility.health_check)


async def get_server_info_tool(request: Request) -> JSONResponse:
    return await _call_tool(_utility.get_server_info)


# ── MCP tool catalog + dispatch (for LLM chat in the UI) ──────────────────


async def list_tools(request: Request) -> JSONResponse:
    """Return every registered @mcp.tool with its JSON Schema, in Anthropic+OpenAI-ready shape."""
    try:
        tools = await mcp.list_tools()
    except Exception as exc:  # noqa: BLE001
        return _err(exc.__class__.__name__, str(exc), 500)

    out: list[dict[str, Any]] = []
    for t in tools:
        schema = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
        out.append(
            {
                "name": t.name,
                "description": (t.description or "").strip(),
                "input_schema": schema,
                "min_role": TOOL_MINIMUM_ROLE.get(t.name, "viewer"),
            }
        )
    return _ok(out)


async def call_tool(request: Request) -> JSONResponse:
    """Invoke a registered MCP tool by name with an arguments dict.

    Body shape::

        {"name": "list_dashboards", "arguments": {"tags": ["prod"], "limit": 20}}

    Role enforcement, pooling, and retries all apply exactly as if the call
    came in through the SSE transport.
    """
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        return _err("ValueError", f"invalid JSON body: {exc}", 400)

    name = body.get("name")
    args = body.get("arguments") or {}
    if not name or not isinstance(name, str):
        return _err("ValueError", "body must include 'name'", 400)
    if not isinstance(args, dict):
        return _err("ValueError", "'arguments' must be an object", 400)

    fn = _TOOL_DISPATCH.get(name)
    if fn is None:
        return _err("UnknownTool", f"no such tool: {name}", 404)

    return await _call_tool(fn, **args)


def routes() -> list[Route]:
    """Return the list of ``/api/*`` routes to mount in the Starlette app."""
    return [
        Route("/api/server-info", server_info),
        Route("/api/environments/{name}", update_environment, methods=["PUT"]),
        Route("/api/environments/{name}/test", test_environment, methods=["POST"]),
        Route("/api/active", set_active, methods=["POST"]),
        Route("/api/dashboards", list_dashboards),
        Route("/api/dashboards/{uid}", get_dashboard),
        Route("/api/datasources", list_datasources),
        Route("/api/folders", list_folders),
        Route("/api/health", health_check),
        Route("/api/info", get_server_info_tool),
        Route("/api/tools", list_tools),
        Route("/api/tools/call", call_tool, methods=["POST"]),
    ]
