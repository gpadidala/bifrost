# Configuration Reference

Bifröst follows the [12-factor](https://12factor.net/config) model: every setting is an environment variable, defaults live in code, and the `.env` file is just a convenience for local dev. The Pydantic Settings module loads `.env` automatically — in containers you typically inject env vars directly.

There are **three** config surfaces:

1. **`packages/core`** — the MCP server. Reads `GRAFANA_MCP_*` env vars (this page).
2. **`packages/sdk`** — the Python SDK. Also reads `GRAFANA_MCP_*` *and* `.grafana-mcp.toml`. See [SDK reference](../api/sdk-reference.md#configuration).
3. **`packages/ui`** — the React app. Reads from `localStorage` (encrypted) plus a small set of `VITE_*` build-time vars.

## Top-level structure

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRAFANA_MCP_", env_file=".env", env_nested_delimiter="__")

    transport: TransportConfig
    environments: dict[str, GrafanaEnvironment]
    active_environment: Literal["dev", "perf", "prod"] = "dev"
    active_role: Literal["viewer", "editor", "admin"] = "viewer"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
```

The `__` delimiter is how you reach into nested fields from env vars. `GRAFANA_MCP_TRANSPORT__PORT=8765` sets `settings.transport.port`. `GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__ADMIN=glsa_xxx` sets `settings.environments["prod"].service_accounts.admin`.

## Active selection

| Variable | Type | Default | Description |
|---|---|---|---|
| `GRAFANA_MCP_ACTIVE_ENVIRONMENT` | `dev` / `perf` / `prod` | `dev` | Which environment the server boots with. Tool calls can override per request. |
| `GRAFANA_MCP_ACTIVE_ROLE` | `viewer` / `editor` / `admin` | `viewer` | Which token the server uses by default. Tool calls can override per request — but only *down*, never *up* without an explicit elevation flag. |

## Transport

| Variable | Type | Default | Description |
|---|---|---|---|
| `GRAFANA_MCP_TRANSPORT__MODE` | `sse` / `http` | `sse` | `sse` for VSCode + UI, `http` for streamable-HTTP clients (SDK, CI). |
| `GRAFANA_MCP_TRANSPORT__HOST` | string | `0.0.0.0` | Bind address. Use `127.0.0.1` to restrict to localhost. |
| `GRAFANA_MCP_TRANSPORT__PORT` | int | `8765` | Listen port. |
| `GRAFANA_MCP_TRANSPORT__PATH_PREFIX` | string | `/mcp` | Path prefix; the SSE endpoint is `{prefix}/sse`, the HTTP endpoint is `{prefix}/messages`. |

See [Transports](../architecture/transports.md) for the protocol-level differences.

## Environment block

Each entry under `GRAFANA_MCP_ENVIRONMENTS__<NAME>__*` becomes a `GrafanaEnvironment` instance. You **must** define at least one environment, and it must match `active_environment`.

| Field | Type | Default | Description |
|---|---|---|---|
| `BASE_URL` | URL | required | Grafana URL with no trailing slash. e.g. `https://grafana.company.com` |
| `TLS_VERIFY` | bool | `true` | Set `false` only for self-signed dev clusters. |
| `TIMEOUT_SECONDS` | float | `30.0` | Per-request HTTP timeout. |
| `RATE_LIMIT_RPS` | float | `10.0` | Max in-flight requests per second across all tokens for this env. Implemented via `asyncio.Semaphore`. |
| `SERVICE_ACCOUNTS__VIEWER` | secret | required | Grafana service-account token with role `Viewer`. |
| `SERVICE_ACCOUNTS__EDITOR` | secret | required | Grafana service-account token with role `Editor`. |
| `SERVICE_ACCOUNTS__ADMIN` | secret | required | Grafana service-account token with role `Admin`. |

> ⚠️ All three tokens are required even if you don't plan to use the higher roles. Bifröst validates the entire env block on startup so you can't get a `KeyError` mid-call months later.

### Example — `prod` environment block

```env
GRAFANA_MCP_ENVIRONMENTS__PROD__BASE_URL=https://grafana.company.com
GRAFANA_MCP_ENVIRONMENTS__PROD__TLS_VERIFY=true
GRAFANA_MCP_ENVIRONMENTS__PROD__TIMEOUT_SECONDS=30
GRAFANA_MCP_ENVIRONMENTS__PROD__RATE_LIMIT_RPS=10
GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__VIEWER=glsa_prod_viewer_xxxxxxxxx
GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__EDITOR=glsa_prod_editor_xxxxxxxxx
GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__ADMIN=glsa_prod_admin_xxxxxxxxx
```

## Logging

| Variable | Type | Default | Description |
|---|---|---|---|
| `GRAFANA_MCP_LOG_LEVEL` | string | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `GRAFANA_MCP_LOG_FORMAT` | `json` / `console` | `console` | `json` for production / log shipping, `console` for local dev. |

`structlog` emits one line per event: tool call, tool result, Grafana request, Grafana response, retry, rate-limit wait. **Authorization headers and any field matching `*token*` are auto-redacted** before serialization — paste log lines freely into bug reports.

## UI configuration (browser)

The React app does **not** read `GRAFANA_MCP_*` env vars. Configuration lives in:

- **`localStorage`** — environments, active env, active role, LLM provider+model+key. Encrypted with a user-set passphrase via Web Crypto API.
- **Build-time `VITE_*` vars** — only `VITE_MCP_SSE_URL` (the SSE endpoint the UI defaults to). Set in `packages/ui/.env` or via `docker compose`.

You can **export your UI config as a `.env` file** from the Connection Config page, which makes it easy to seed a teammate or move from dev to a workstation.

## Config validation

```bash
grafana-mcp validate-config
```

This loads `.env`, instantiates `Settings`, ping-tests every environment + role pair, and prints a table:

```
Environment   Role     URL                                Status      Latency
dev           viewer   http://localhost:3000              ✓ ok        12 ms
dev           editor   http://localhost:3000              ✓ ok        14 ms
dev           admin    http://localhost:3000              ✓ ok        13 ms
prod          viewer   https://grafana.company.com        ✓ ok        87 ms
prod          editor   https://grafana.company.com        ✗ 401       —
prod          admin    https://grafana.company.com        ✓ ok        91 ms
```

Run this in CI before deploying — it catches token rotation lapses fast.
