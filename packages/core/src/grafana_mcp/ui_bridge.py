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

import io
import time
import zipfile
from typing import Any

from pydantic import BaseModel, SecretStr
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
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
    "create_dashboard": _dashboards.create_dashboard,
    "create_smart_dashboard": _dashboards.create_smart_dashboard,
    "update_dashboard": _dashboards.update_dashboard,
    "delete_dashboard": _dashboards.delete_dashboard,
    "list_datasources": _datasources.list_datasources,
    "get_datasource": _datasources.get_datasource,
    "query_datasource": _datasources.query_datasource,
    "list_folders": _folders.list_folders,
    "create_folder": _folders.create_folder,
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


# ── Python SDK zip download ────────────────────────────────────────────────


def _sdk_readme(base_url: str, env: str, role: str) -> str:
    return f"""# Bifröst Python SDK

A tiny, dependency-light Python client for the Bifröst MCP server at
**`{base_url}`**. No MCP protocol plumbing — just plain HTTP against the
REST bridge exposed at `/api/*`. Every call goes through the same typed
tool functions, role enforcement, connection pool, and retry layer that
an MCP client would use.

## What's in this bundle

| File | What it does |
|------|---|
| `bifrost_client.py`       | Synchronous client class — drop into scripts, notebooks, CI |
| `bifrost_async.py`        | Async version for concurrent tool calls |
| `example_quickstart.py`   | 10-line "hello world" that lists dashboards |
| `example_parallel.py`     | Fans out 4 tool calls in parallel via asyncio |
| `example_role_switch.py`  | Switches role mid-session to call an editor-only tool |
| `requirements.txt`        | Pins `httpx>=0.27` |
| `README.md`               | This file |

## Install

```bash
# Unzip + create a venv
unzip bifrost-sdk.zip
cd bifrost-sdk
python -m venv .venv
source .venv/bin/activate

# One dependency
pip install -r requirements.txt
```

## Run the quick-start

```bash
python example_quickstart.py
```

Expected output (pointed at **{base_url}**, env **{env}**, role **{role}**):

```
Bifröst v1.3.0  env={env}  role={role}
✓ Grafana <version>  db=ok
N dashboards across M folders
```

If you get a `ConnectionError`, the Bifröst server is not reachable at
`{base_url}`. Start it with:

```bash
grafana-mcp serve --transport sse --env {env} --role {role} --port 8765
```

## The three patterns

### 1. `bifrost_client.py` — sync

```python
from bifrost_client import BifrostClient

c = BifrostClient()
print(c.server_info())
print(len(c.list_dashboards()), "dashboards")
print(c.call_tool("list_dashboards", tags=["production"], limit=50))
```

Good for: notebooks, CI checks, throwaway scripts.

### 2. `bifrost_async.py` — async

```python
import asyncio
from bifrost_async import BifrostAsyncClient

async def main():
    async with BifrostAsyncClient() as c:
        info, health, dashboards = await asyncio.gather(
            c.server_info(),
            c.health(),
            c.list_dashboards(),
        )
        print(info, health, len(dashboards))

asyncio.run(main())
```

Good for: parallel tool calls, long-running services, integration with
async frameworks (FastAPI, aiohttp).

### 3. Generic `call_tool` — any MCP tool by name

Both clients expose `call_tool(name, **args)` that dispatches to any of
Bifröst's 16 MCP tools. Same role enforcement as a native MCP client:

- `viewer`  — all read tools
- `editor`  — adds `silence_alert`
- `admin`   — adds `list_users`, `list_service_accounts`

If you call a tool with insufficient role, the SDK raises
`PermissionError` with a clear message. Switch the active role in
Bifröst (via the UI Settings drawer or `POST /api/active`) and retry.

## Configuration

The clients default to the URL this bundle was generated against:

- **BASE_URL:** `{base_url}`

You can override at construction time:

```python
from bifrost_client import BifrostClient

c = BifrostClient(base_url="http://other-host:8765")
```

## License

MIT — same as Bifröst.

## Regenerating this bundle

The zip is served fresh each time you click the **Download SDK** button
in the Bifröst UI (Python SDK tab). It bakes in the URL, env, and role
of the server you're looking at, so re-downloading after changing
active env/role gives you a pre-configured copy.
"""


def _sdk_sync_client(base_url: str) -> str:
    return f'''"""Bifröst Python SDK — synchronous client.

Requires: httpx>=0.27
Install:  pip install -r requirements.txt
"""
from __future__ import annotations

from typing import Any

import httpx

DEFAULT_BASE_URL = "{base_url}"


class BifrostError(Exception):
    """Raised when Bifröst returns ok:false."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"{{kind}}: {{message}}")
        self.kind = kind
        self.message = message


class BifrostClient:
    """Synchronous client for the Bifröst REST bridge.

    Every method round-trips to the Bifröst server, which in turn calls
    the underlying MCP tool function (with role enforcement, pool reuse,
    and retry). The client itself holds no Grafana credentials — all
    authentication happens server-side via the configured service
    account tokens.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ── context manager so you can `with BifrostClient() as c:` ─────────
    def __enter__(self) -> "BifrostClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # ── low-level helpers ───────────────────────────────────────────────
    def _get(self, path: str, params: dict | None = None) -> Any:
        r = self._http.get(path, params=params)
        r.raise_for_status()
        env = r.json()
        if not env.get("ok"):
            raise BifrostError(env.get("error", "Error"), env.get("message", ""))
        return env["data"]

    def _post(self, path: str, body: dict) -> Any:
        r = self._http.post(path, json=body)
        r.raise_for_status()
        env = r.json()
        if not env.get("ok"):
            raise BifrostError(env.get("error", "Error"), env.get("message", ""))
        return env["data"]

    # ── server state ────────────────────────────────────────────────────
    def server_info(self) -> dict:
        return self._get("/api/server-info")

    def health(self) -> dict:
        return self._get("/api/health")

    # ── read tools ──────────────────────────────────────────────────────
    def list_dashboards(
        self,
        *,
        tags: list[str] | None = None,
        folder_uid: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        params: dict[str, Any] = {{"limit": limit}}
        if folder_uid:
            params["folder_uid"] = folder_uid
        if tags:
            params["tag"] = tags
        return self._get("/api/dashboards", params=params)

    def get_dashboard(self, uid: str) -> dict:
        return self._get(f"/api/dashboards/{{uid}}")

    def list_datasources(self) -> list[dict]:
        return self._get("/api/datasources")

    def list_folders(self) -> list[dict]:
        return self._get("/api/folders")

    def list_tools(self) -> list[dict]:
        """Return the full MCP tool catalog with JSON schemas."""
        return self._get("/api/tools")

    # ── generic tool dispatch ───────────────────────────────────────────
    def call_tool(self, name: str, /, **arguments: Any) -> Any:
        """Call any registered MCP tool by name.

        Available tools include: list_dashboards, search_dashboards,
        get_dashboard, get_dashboard_panels, list_datasources,
        get_datasource, query_datasource, list_folders,
        list_alert_rules, get_alert_rule, list_alert_instances,
        silence_alert, list_users, list_service_accounts, health_check,
        get_server_info.
        """
        return self._post("/api/tools/call", {{"name": name, "arguments": arguments}})

    # ── runtime configuration ───────────────────────────────────────────
    def set_active(
        self,
        *,
        environment: str | None = None,
        role: str | None = None,
    ) -> dict:
        """Switch the active env / role on the Bifröst server."""
        patch: dict[str, str] = {{}}
        if environment:
            patch["environment"] = environment
        if role:
            patch["role"] = role
        return self._post("/api/active", patch)
'''


def _sdk_async_client(base_url: str) -> str:
    return f'''"""Bifröst Python SDK — asynchronous client.

Requires: httpx>=0.27
Install:  pip install -r requirements.txt
"""
from __future__ import annotations

from typing import Any

import httpx

DEFAULT_BASE_URL = "{base_url}"


class BifrostError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"{{kind}}: {{message}}")
        self.kind = kind
        self.message = message


class BifrostAsyncClient:
    """Async client for the Bifröst REST bridge."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def __aenter__(self) -> "BifrostAsyncClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        r = await self._http.get(path, params=params)
        r.raise_for_status()
        env = r.json()
        if not env.get("ok"):
            raise BifrostError(env.get("error", "Error"), env.get("message", ""))
        return env["data"]

    async def _post(self, path: str, body: dict) -> Any:
        r = await self._http.post(path, json=body)
        r.raise_for_status()
        env = r.json()
        if not env.get("ok"):
            raise BifrostError(env.get("error", "Error"), env.get("message", ""))
        return env["data"]

    async def server_info(self) -> dict:
        return await self._get("/api/server-info")

    async def health(self) -> dict:
        return await self._get("/api/health")

    async def list_dashboards(
        self,
        *,
        tags: list[str] | None = None,
        folder_uid: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        params: dict[str, Any] = {{"limit": limit}}
        if folder_uid:
            params["folder_uid"] = folder_uid
        if tags:
            params["tag"] = tags
        return await self._get("/api/dashboards", params=params)

    async def get_dashboard(self, uid: str) -> dict:
        return await self._get(f"/api/dashboards/{{uid}}")

    async def list_datasources(self) -> list[dict]:
        return await self._get("/api/datasources")

    async def list_folders(self) -> list[dict]:
        return await self._get("/api/folders")

    async def list_tools(self) -> list[dict]:
        return await self._get("/api/tools")

    async def call_tool(self, name: str, /, **arguments: Any) -> Any:
        return await self._post("/api/tools/call", {{"name": name, "arguments": arguments}})

    async def set_active(
        self,
        *,
        environment: str | None = None,
        role: str | None = None,
    ) -> dict:
        patch: dict[str, str] = {{}}
        if environment:
            patch["environment"] = environment
        if role:
            patch["role"] = role
        return await self._post("/api/active", patch)
'''


def _sdk_example_quickstart(base_url: str, env: str, role: str) -> str:
    return f'''"""Quick-start — lists dashboards in the active environment.

Run:  python example_quickstart.py
"""
from bifrost_client import BifrostClient

# Defaults to {base_url} but you can override
with BifrostClient() as c:
    info = c.server_info()
    print(f"Bifröst v{{info['version']}}  env={{info['active_environment']}}  role={{info['active_role']}}")

    health = c.health()
    print(f"{{'✓' if health['database'] == 'ok' else '✗'}} Grafana {{health['version']}}  db={{health['database']}}")

    dashboards = c.list_dashboards(limit=500)
    folders = {{d.get("folder_title") or "General" for d in dashboards}}
    print(f"{{len(dashboards)}} dashboards across {{len(folders)}} folders")

    datasources = c.list_datasources()
    print(f"{{len(datasources)}} datasources:")
    for ds in datasources[:10]:
        marker = " ★" if ds.get("is_default") else ""
        print(f"  • {{ds['name']}}  ({{ds['type']}}){{marker}}")
'''


def _sdk_example_parallel(base_url: str) -> str:
    return f'''"""Parallel example — fans out 4 tool calls via asyncio.gather.

Run:  python example_parallel.py
"""
import asyncio

from bifrost_async import BifrostAsyncClient


async def main() -> None:
    async with BifrostAsyncClient() as c:
        info, health, dashboards, datasources = await asyncio.gather(
            c.server_info(),
            c.health(),
            c.list_dashboards(limit=500),
            c.list_datasources(),
        )
        print(f"Bifröst  env={{info['active_environment']}}  role={{info['active_role']}}")
        print(f"Grafana  v{{health['version']}}  db={{health['database']}}")
        print(f"{{len(dashboards)}} dashboards · {{len(datasources)}} datasources")

        # Fan out to get_dashboard in parallel for the first 5
        detailed = await asyncio.gather(
            *(c.get_dashboard(d["uid"]) for d in dashboards[:5])
        )
        print(f"Fetched {{len(detailed)}} full dashboards in parallel")


if __name__ == "__main__":
    asyncio.run(main())
'''


def _sdk_example_role_switch() -> str:
    return '''"""Role-switch example — elevate to editor to silence an alert.

Run:  python example_role_switch.py

NOTE: Requires the Bifröst server to have been started with --role admin
(or at least --role editor) so runtime role escalation is allowed.
"""
from bifrost_client import BifrostClient, BifrostError

with BifrostClient() as c:
    # Start in viewer mode — can only read
    c.set_active(role="viewer")
    print("role: viewer")

    try:
        c.call_tool(
            "silence_alert",
            matchers=[{"name": "alertname", "value": "HighCPU", "isEqual": True}],
            duration_minutes=30,
            comment="scheduled maintenance",
        )
    except BifrostError as exc:
        print(f"  expected failure: {exc}")

    # Elevate to editor — now the write tool works
    c.set_active(role="editor")
    print("role: editor")

    try:
        silence = c.call_tool(
            "silence_alert",
            matchers=[{"name": "alertname", "value": "HighCPU", "isEqual": True}],
            duration_minutes=30,
            comment="scheduled maintenance",
        )
        print(f"  silenced: {silence}")
    except BifrostError as exc:
        print(f"  silence failed: {exc}")
    finally:
        # Always drop back to the safest role
        c.set_active(role="viewer")
        print("role: viewer (restored)")
'''


def _sdk_requirements() -> str:
    return "httpx>=0.27\n"


async def download_sdk(request: Request) -> Response:
    """Stream a zip file containing the Python SDK bundle, parameterized
    with the live ``base_url``, env, and role of the server the user is
    currently looking at.

    Query params:
        base_url  Override the base URL baked into the bundle. Defaults
                  to the request's own base URL (so you get the same
                  origin the browser is already hitting).
    """
    settings = _state.get_settings()
    env = settings.active_environment
    role = settings.active_role

    base_url = request.query_params.get("base_url")
    if not base_url:
        base_url = str(request.base_url).rstrip("/")
    base_url = base_url.rstrip("/")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        root = "bifrost-sdk/"
        zf.writestr(root + "README.md", _sdk_readme(base_url, env, role))
        zf.writestr(root + "bifrost_client.py", _sdk_sync_client(base_url))
        zf.writestr(root + "bifrost_async.py", _sdk_async_client(base_url))
        zf.writestr(root + "example_quickstart.py", _sdk_example_quickstart(base_url, env, role))
        zf.writestr(root + "example_parallel.py", _sdk_example_parallel(base_url))
        zf.writestr(root + "example_role_switch.py", _sdk_example_role_switch())
        zf.writestr(root + "requirements.txt", _sdk_requirements())

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="bifrost-sdk.zip"',
            "Content-Length": str(len(buf.getvalue())),
        },
    )


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
        Route("/api/sdk/download", download_sdk),
    ]
