# Python SDK Reference

The complete API reference for `grafana-mcp-sdk`. For the higher-level usage walkthrough, see [`packages/sdk`](../packages/sdk.md).

## Install

```bash
pip install grafana-mcp-sdk
```

## Top-level imports

```python
from grafana_mcp_sdk import (
    GrafanaMCP,           # the main entry point
    GrafanaSession,       # what mcp.connect() yields
    GrafanaError,         # raised on Grafana 4xx/5xx
    PermissionError,      # raised on insufficient role
    configure_logging,    # opt-in structlog
)
```

All Pydantic schemas are re-exported from `grafana_mcp_sdk.schemas`:

```python
from grafana_mcp_sdk.schemas import (
    DashboardSummary, DashboardDetail, Panel,
    DatasourceSummary, DatasourceDetail, QueryResult,
    AlertRule, AlertRuleDetail, AlertInstance, Silence,
    Folder, UserSummary, ServiceAccount,
    HealthStatus, ServerInfo,
    TimeRange,
)
```

## `GrafanaMCP` constructor

```python
class GrafanaMCP:
    def __init__(
        self,
        environment: Literal["dev", "perf", "prod"],
        role: Literal["viewer", "editor", "admin"],
        base_url: str | AnyHttpUrl,
        service_accounts: ServiceAccountSet | dict[str, str],
        tls_verify: bool = True,
        timeout_seconds: float = 30.0,
        rate_limit_rps: float = 10.0,
    ) -> None: ...
```

`service_accounts` accepts either a `ServiceAccountSet` Pydantic model or a plain dict with the three role keys:

```python
mcp = GrafanaMCP(
    environment="dev",
    role="editor",
    base_url="http://localhost:3000",
    service_accounts={
        "viewer": "glsa_viewer_xxx",
        "editor": "glsa_editor_xxx",
        "admin":  "glsa_admin_xxx",
    },
)
```

## Class-method constructors

### `from_env()`

```python
@classmethod
def from_env(cls) -> GrafanaMCP: ...
```

Loads from `GRAFANA_MCP_*` environment variables. Auto-discovers `.grafana-mcp.toml` in the current dir or any parent. Falls back to `~/.config/grafana-mcp/config.toml`. Raises `ConfigError` if no source has the required fields.

### `from_toml(path)`

```python
@classmethod
def from_toml(cls, path: str | Path) -> GrafanaMCP: ...
```

Loads from a specific TOML file. Supports `${VAR}` env-var interpolation in token fields.

### `from_dict(data)`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> GrafanaMCP: ...
```

Loads from a plain Python dict (matching the TOML structure). Useful in tests.

## Connecting

### `mcp.connect()` — async

```python
async with mcp.connect() as g:
    dashboards = await g.list_dashboards()
```

`g` is a `GrafanaSession` with one async method per MCP tool. The session pings Grafana on enter and tears down the underlying `httpx.AsyncClient` on exit.

### `mcp.sync()` — sync wrapper

```python
with mcp.sync() as g:
    dashboards = g.list_dashboards()
```

Runs the async session under a hidden `asyncio.Runner`. Methods are sync-callable. **Don't mix with `connect()` in the same process.**

## `GrafanaSession`

### Tool methods

Every method on `GrafanaSession` matches a tool from [MCP Tools Reference](mcp-tools-reference.md). Same signature, same return type, same role enforcement.

```python
async def list_dashboards(self, folder_uid: str | None = None, tags: list[str] | None = None, limit: int = 100) -> list[DashboardSummary]: ...
async def get_dashboard(self, uid: str) -> DashboardDetail: ...
async def search_dashboards(self, query: str, type: Literal["dash-db", "dash-folder"] = "dash-db") -> list[SearchResult]: ...
async def get_dashboard_panels(self, uid: str) -> list[Panel]: ...

async def list_datasources(self) -> list[DatasourceSummary]: ...
async def get_datasource(self, uid: str) -> DatasourceDetail: ...
async def query_datasource(self, datasource_uid: str, query: str, time_range: TimeRange) -> QueryResult: ...

async def list_alert_rules(self, folder_uid: str | None = None) -> list[AlertRule]: ...
async def get_alert_rule(self, uid: str) -> AlertRuleDetail: ...
async def list_alert_instances(self, state: Literal["firing", "normal", "pending", "no_data"] | None = None) -> list[AlertInstance]: ...
async def silence_alert(self, matcher: str, duration_minutes: int, comment: str) -> Silence: ...    # editor

async def list_folders(self) -> list[Folder]: ...

async def list_users(self) -> list[UserSummary]: ...                                                # admin
async def list_service_accounts(self) -> list[ServiceAccount]: ...                                   # admin

async def health_check(self, environment: EnvName | None = None) -> HealthStatus: ...
async def get_server_info(self) -> ServerInfo: ...
```

The sync session has the same methods, without `async`.

### `as_role(role)` — temporary role escalation

```python
async with g.as_role("admin") as admin_g:
    users = await admin_g.list_users()
# back to original role here
```

`admin_g` is a fresh `GrafanaSession` bound to the new role. The original `g` is unchanged. The new session shares the underlying connection pool when possible.

### `as_environment(env)` — temporary env switch

```python
async with g.as_environment("prod") as prod_g:
    prod_dashboards = await prod_g.list_dashboards()
```

Symmetric to `as_role`. Swaps the env for the duration of the block.

### `close()`

```python
await g.close()
```

Manually close the underlying `httpx.AsyncClient`. Normally called automatically by the context manager — only use this if you can't use a `with` block.

## Configuration

The SDK reads config from these sources, in order:

1. Explicit constructor arguments
2. `.grafana-mcp.toml` in the current dir or any parent dir
3. `GRAFANA_MCP_*` environment variables
4. `~/.config/grafana-mcp/config.toml`

### `.grafana-mcp.toml` schema

```toml
[defaults]
environment = "dev"          # default env if not specified at construct time
role = "viewer"              # default role

[environments.dev]
base_url = "http://localhost:3000"
tls_verify = false
timeout_seconds = 30
rate_limit_rps = 20

[environments.dev.service_accounts]
viewer = "glsa_xxx"
editor = "glsa_yyy"
admin  = "glsa_zzz"

[environments.prod]
base_url = "https://grafana.company.com"
tls_verify = true

[environments.prod.service_accounts]
viewer = "${PROD_VIEWER_TOKEN}"     # env var interpolation
editor = "${PROD_EDITOR_TOKEN}"
admin  = "${PROD_ADMIN_TOKEN}"
```

### Env var schema

Same as the server (`GRAFANA_MCP_*`). See [Configuration Reference](../getting-started/configuration.md).

## Errors

```python
from grafana_mcp_sdk import GrafanaError, PermissionError

try:
    silence = await g.silence_alert(matcher='{job="api"}', duration_minutes=30, comment="deploy")
except PermissionError as e:
    # Active role below 'editor'
    print(e)
except GrafanaError as e:
    # Grafana returned 4xx/5xx after retries
    print(f"Grafana error {e.status_code}: {e.response_body}")
```

| Exception | Attributes |
|---|---|
| `PermissionError` | `tool_name`, `required_role`, `active_role` |
| `GrafanaError` | `status_code`, `response_body`, `request_path` |
| `ValidationError` | `field`, `expected`, `got` (from Pydantic) |
| `ConnectionError` | `cause` (the underlying `httpx` exception) |
| `TimeoutError` | `timeout_seconds`, `request_path` |
| `RateLimitError` | `queue_depth`, `wait_seconds` |

## Logging

By default the SDK is silent. Opt in with:

```python
from grafana_mcp_sdk import configure_logging
configure_logging(level="INFO", fmt="console")
```

In CI, use `fmt="json"` so log shippers can parse it. Auth headers and any field matching `*token*` are auto-redacted.

## CLI — `grafana-sdk`

```bash
grafana-sdk --version
grafana-sdk init                                    # write a starter .grafana-mcp.toml
grafana-sdk connect --env dev --role viewer         # ping test
grafana-sdk list-tools                              # show every tool with its signature
grafana-sdk run <tool> [--key value ...]            # invoke a tool
grafana-sdk shell --env dev --role editor           # interactive REPL
grafana-sdk health                                  # ping every (env, role) pair
```

### `run` command argument mapping

CLI flags map to tool kwargs by replacing underscores with dashes:

| Tool kwarg | CLI flag |
|---|---|
| `folder_uid="abc"` | `--folder-uid abc` |
| `tags=["a","b"]` | `--tags a --tags b` (repeat) |
| `limit=50` | `--limit 50` |
| `time_range={"from":...,"to":...}` | `--from 2026-04-12T00:00:00Z --to 2026-04-12T01:00:00Z` |

The CLI prints results as JSON to stdout. Errors go to stderr with a non-zero exit.

## Type stubs

The SDK ships with full type stubs (`py.typed` marker). `mypy` and `pyright` work with no extra config.
