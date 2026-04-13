# `packages/core` — Python MCP Server

`packages/core` is the Python MCP server at the heart of Bifröst. It registers ~20 typed tools, enforces role minimums, manages a pool of `httpx` clients per environment+role pair, and exposes the whole thing over either SSE or streamable HTTP.

## Layout

```
packages/core/
├── pyproject.toml
├── src/grafana_mcp/
│   ├── __init__.py
│   ├── cli.py                 # grafana-mcp CLI entry points
│   ├── server.py              # FastAPI app + MCP wiring
│   ├── settings.py            # Pydantic Settings (12-factor config)
│   ├── rbac.py                # ROLE_HIERARCHY + TOOL_MINIMUM_ROLE + enforce_role
│   ├── client/
│   │   ├── __init__.py
│   │   ├── grafana.py         # GrafanaClient (httpx wrapper)
│   │   ├── pool.py            # ClientPool (one client per env+role)
│   │   └── retry.py           # tenacity retry policies
│   ├── schemas/
│   │   ├── dashboard.py       # DashboardSummary, DashboardDetail, Panel, ...
│   │   ├── datasource.py      # DatasourceSummary, DatasourceDetail, QueryResult
│   │   ├── alert.py           # AlertRule, AlertRuleDetail, AlertInstance, Silence
│   │   ├── folder.py          # Folder, FolderTree
│   │   ├── user.py            # UserSummary, ServiceAccount
│   │   └── common.py          # HealthStatus, ServerInfo, error envelopes
│   ├── tools/
│   │   ├── __init__.py        # Registers every tool with the MCP instance
│   │   ├── dashboards.py      # list/get/search/get_panels
│   │   ├── datasources.py     # list/get/query
│   │   ├── alerts.py          # rules + instances + silence_alert
│   │   ├── folders.py         # list_folders
│   │   ├── users.py           # list_users, list_service_accounts (admin)
│   │   └── utility.py         # health_check, get_server_info
│   ├── transports/
│   │   ├── sse.py             # SSE transport binding
│   │   └── http.py            # streamable HTTP transport binding
│   └── logging.py             # structlog setup + auth-header redaction
└── tests/
    ├── conftest.py
    ├── test_settings.py
    ├── test_rbac.py
    ├── client/
    │   ├── test_grafana.py    # respx-mocked
    │   ├── test_pool.py
    │   └── test_retry.py
    └── tools/
        ├── test_dashboards.py
        ├── test_datasources.py
        ├── test_alerts.py
        └── test_utility.py
```

## CLI

The package installs a single console script — `grafana-mcp` — defined in `pyproject.toml`:

```toml
[project.scripts]
grafana-mcp = "grafana_mcp.cli:app"
```

### Commands

```bash
grafana-mcp serve [OPTIONS]
grafana-mcp validate-config
grafana-mcp list-tools
grafana-mcp health
grafana-mcp --version
```

#### `serve` — boot the MCP server

```bash
grafana-mcp serve \
  --transport sse \              # sse | http
  --host 0.0.0.0 \               # bind address
  --port 8765 \                  # listen port
  --env dev \                    # dev | perf | prod
  --role viewer \                # viewer | editor | admin
  --log-level INFO \             # DEBUG | INFO | WARNING | ERROR
  --log-format console           # console | json
```

Every flag has an environment-variable counterpart (`GRAFANA_MCP_*`). CLI flags win over env vars.

#### `validate-config` — dry-run config check

Loads `.env`, instantiates `Settings`, ping-tests every (env, role) pair, and prints a status table. Used in CI before deploys.

#### `list-tools` — print the registered tool catalog

```bash
$ grafana-mcp list-tools

Tool                        Min Role   Description
─────────────────────────── ────────── ────────────────────────────────────
list_dashboards             viewer     List dashboards in a folder
get_dashboard               viewer     Get a dashboard by UID
search_dashboards           viewer     Full-text dashboard search
get_dashboard_panels        viewer     List panels in a dashboard
list_datasources            viewer     List all configured datasources
get_datasource              viewer     Get a datasource by UID
query_datasource            viewer     Run a query against a datasource
list_alert_rules            viewer     List alert rules
get_alert_rule              viewer     Get an alert rule by UID
list_alert_instances        viewer     List firing/normal/pending alert instances
silence_alert               editor     Silence matching alerts for N minutes
list_folders                viewer     List Grafana folders
list_users                  admin      List org users
list_service_accounts       admin      List Grafana service accounts
health_check                viewer     Ping Grafana, return health
get_server_info             viewer     Bifröst version + Grafana version + uptime
```

#### `health` — ping every configured environment

```bash
$ grafana-mcp health

dev    viewer  ✓ ok  (12 ms)
dev    editor  ✓ ok  (14 ms)
dev    admin   ✓ ok  (13 ms)
prod   viewer  ✓ ok  (87 ms)
prod   editor  ✗ 401 (token rotated?)
prod   admin   ✓ ok  (91 ms)
```

Exits with code `0` if everything is healthy, `1` otherwise. Useful as a CI gate.

## The GrafanaClient

```python
class GrafanaClient:
    """Typed async Grafana HTTP client with retry, rate limiting, and token injection."""

    def __init__(self, env: GrafanaEnvironment, role: GrafanaRole) -> None:
        self.env = env
        self.role = role
        self._client = httpx.AsyncClient(
            base_url=str(env.base_url),
            timeout=env.timeout_seconds,
            verify=env.tls_verify,
            http2=True,
            headers={"Authorization": f"Bearer {env.service_accounts.token_for(role).get_secret_value()}"},
        )
        self._semaphore = asyncio.Semaphore(int(env.rate_limit_rps))

    async def get(self, path: str, params: dict | None = None) -> Any: ...
    async def post(self, path: str, body: dict) -> Any: ...
    async def put(self, path: str, body: dict) -> Any: ...
    async def delete(self, path: str) -> Any: ...

    async def close(self) -> None:
        await self._client.aclose()
```

Each method:

1. Acquires the semaphore (rate limit gate)
2. Calls the underlying httpx method through a `tenacity` retry decorator
3. Logs the request and response via `structlog` with auth headers redacted
4. Raises `GrafanaError` (subclass of `Exception`) on non-2xx after retries
5. Returns `response.json()` on success

The retry policy is:

```python
@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    reraise=True,
)
```

Only 429 and 5xx are retried. 4xx (other than 429) is a client error and fails immediately.

## The pool

`ClientPool` keeps one `GrafanaClient` per (env_name, role) tuple, lazily built:

```python
class ClientPool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: dict[tuple[str, str], GrafanaClient] = {}

    async def get(self, env_name: str, role: GrafanaRole) -> GrafanaClient:
        key = (env_name, role)
        if key not in self._clients:
            env = self._settings.environments[env_name]
            self._clients[key] = GrafanaClient(env, role)
        return self._clients[key]

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
```

The pool is built once at server startup, scoped to the FastAPI app lifespan, and torn down on shutdown.

## Tool function shape

Every tool follows the same shape:

```python
@mcp.tool()
async def list_dashboards(
    folder_uid: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
    *,
    environment: Literal["dev", "perf", "prod"] | None = None,
    role: GrafanaRole | None = None,
) -> list[DashboardSummary]:
    """List dashboards, optionally filtered by folder and tags."""
    env_name = environment or settings.active_environment
    active_role = role or settings.active_role

    await enforce_role("list_dashboards", active_role)

    client = await pool.get(env_name, active_role)
    raw = await client.get("/api/search", params={
        "type": "dash-db",
        "folderUIDs": folder_uid,
        "tag": tags,
        "limit": limit,
    })
    return [DashboardSummary.model_validate(item) for item in raw]
```

Five things to notice:

1. **Typed params** — Pydantic generates the MCP input schema from these annotations.
2. **`environment` and `role` are keyword-only overrides** — explicit at the call site, never accidentally positional.
3. **Role enforcement happens before any HTTP call** — `enforce_role` raises before `pool.get`.
4. **Output is a Pydantic model** — generates the MCP output schema, type-checked, ready to serialize.
5. **Docstring becomes the tool description** — the LLM reads this when picking which tool to call.

## Logging

`structlog` is configured in `logging.py`:

```python
def configure_logging(level: str, fmt: Literal["json", "console"]) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_auth_headers,                            # custom processor
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    structlog.configure(processors=processors, ...)
```

The `redact_auth_headers` processor walks the event dict and replaces any value at a key matching `*token*`, `*authorization*`, or `*api_key*` with `"<redacted>"`. Tested with regex coverage in `tests/test_logging.py`.

## Tests

```bash
make core-test
```

90% line coverage gate (configured in `pyproject.toml`). HTTP calls are mocked with `respx`:

```python
@pytest.mark.asyncio
async def test_list_dashboards(respx_mock, dev_env):
    respx_mock.get("http://localhost:3000/api/search").mock(
        return_value=httpx.Response(200, json=[
            {"uid": "abc", "title": "Foo", "type": "dash-db", "folderTitle": "General"},
        ])
    )
    client = GrafanaClient(dev_env, role="viewer")
    result = await list_dashboards()
    assert len(result) == 1
    assert result[0].uid == "abc"
```

Every tool has at least one happy-path test, one role-rejection test (call with insufficient role, expect `PermissionError`), and one Grafana-error test.

## Extending

Adding a new tool is a four-step recipe:

1. Add input/output Pydantic models in `schemas/`.
2. Add the async function in the right `tools/` module, decorated with `@mcp.tool()`.
3. If it's not a `viewer`-level tool, add an entry to `TOOL_MINIMUM_ROLE` in `rbac.py`.
4. Write a respx-mocked test in `tests/tools/`.

CI runs a check that every registered tool has a corresponding test file and an entry (or explicit comment) in `TOOL_MINIMUM_ROLE`.
