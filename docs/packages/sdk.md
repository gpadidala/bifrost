# `packages/sdk` — Python Developer SDK

`grafana-mcp-sdk` is a clean Python SDK that developers install locally and use in scripts, notebooks, and CI without running an MCP server. Same role model, same retry policy, same tool surface as `packages/core` — but as an idiomatic Python library, not a JSON-RPC server.

## Why a separate package?

Two reasons:

1. **Smaller footprint.** Notebook users don't want FastAPI, uvicorn, and the MCP transport machinery — they just want `g.list_dashboards()`.
2. **Different lifecycle.** The server runs continuously; the SDK is one-shot. The retry/pool/auth code is shared via a `_internal/` module that both packages depend on through `uv` workspaces.

## Install

```bash
pip install grafana-mcp-sdk
# or
uv add grafana-mcp-sdk
# or, in the workspace:
uv pip install -e packages/sdk
```

Verify:

```bash
grafana-sdk --version
```

## Usage — async (the canonical form)

```python
from grafana_mcp_sdk import GrafanaMCP

mcp = GrafanaMCP(
    environment="dev",
    role="editor",
    base_url="http://localhost:3000",
    service_accounts={
        "viewer": "glsa_viewer_token",
        "editor": "glsa_editor_token",
        "admin":  "glsa_admin_token",
    },
)

async with mcp.connect() as g:
    dashboards = await g.list_dashboards(tags=["production"])
    health     = await g.health_check()
    alerts     = await g.list_alert_instances(state="firing")

    print(f"{len(dashboards)} prod dashboards, {len(alerts)} firing alerts")
```

`mcp.connect()` returns an async context manager that:

1. Builds the `GrafanaClient` for the active env+role
2. Pings Grafana to validate connectivity
3. Yields a `GrafanaSession` (the `g` above) with one method per MCP tool
4. Closes the underlying `httpx.AsyncClient` on exit

Every method on `g` is the **exact same async function** that's registered as an MCP tool in core. Same input types, same output types, same role enforcement. The SDK is just a thinner wrapper.

## Usage — sync (notebooks and scripts)

```python
with mcp.sync() as g:
    dashboards = g.list_dashboards()
    print(dashboards)
```

The sync wrapper runs the async session under a hidden `asyncio.Runner`. It's not as fast as native async (no concurrency), but it's the right answer for Jupyter cells, throwaway scripts, and `if __name__ == "__main__"` demos.

> ⚠️ Don't mix `sync()` and `connect()` in the same process — pick one. The sync wrapper installs its own event loop policy and doesn't play nicely with notebooks that already have one (modern Jupyter is fine; some older versions are not).

## Mid-session role switching

```python
async with mcp.connect() as g:
    info = await g.get_dashboard("abc123")              # uses 'editor' (active)

    async with g.as_role("admin") as admin_g:
        users = await admin_g.list_users()              # uses 'admin' (escalated)

    # back to 'editor' here
    await g.silence_alert(matcher='{job="api"}', duration_minutes=30)
```

`as_role` is a context manager that swaps the underlying `GrafanaClient` for one bound to the new role for the duration of the block. Same env, different token. Clean snap-back.

## Mid-session environment switching

```python
async with mcp.connect() as g:
    dev_dashboards = await g.list_dashboards()              # active env (dev)

    async with g.as_environment("prod") as prod_g:
        prod_dashboards = await prod_g.list_dashboards()    # prod
```

Symmetric to `as_role`.

## Configuration sources (priority order)

1. **Explicit constructor arguments** — wins over everything
2. **`.grafana-mcp.toml`** in the current dir or any parent dir
3. **Environment variables** — same `GRAFANA_MCP_*` schema as the server
4. **`~/.config/grafana-mcp/config.toml`** — global default, last resort

```python
from grafana_mcp_sdk import GrafanaMCP

# Explicit
mcp = GrafanaMCP(environment="prod", role="viewer", base_url="...", service_accounts=...)

# From .grafana-mcp.toml or env vars (auto-discovered)
mcp = GrafanaMCP.from_env()

# From a specific TOML file
mcp = GrafanaMCP.from_toml("/path/to/config.toml")
```

### `.grafana-mcp.toml` format

```toml
[defaults]
environment = "dev"
role = "viewer"

[environments.dev]
base_url = "http://localhost:3000"
tls_verify = false
timeout_seconds = 30
rate_limit_rps = 20

[environments.dev.service_accounts]
viewer = "glsa_viewer_xxxx"
editor = "glsa_editor_xxxx"
admin  = "glsa_admin_xxxx"

[environments.prod]
base_url = "https://grafana.company.com"
tls_verify = true

[environments.prod.service_accounts]
viewer = "${PROD_VIEWER_TOKEN}"   # env var interpolation
editor = "${PROD_EDITOR_TOKEN}"
admin  = "${PROD_ADMIN_TOKEN}"
```

`${VAR}` interpolation lets you keep secrets in env vars while keeping URLs and TLS config in version control. Missing env vars raise on load — never silently empty.

## Developer CLI — `grafana-sdk`

The SDK ships with a CLI distinct from the server's `grafana-mcp`. It's there for ad-hoc work that doesn't need a notebook.

```bash
# Test connectivity
grafana-sdk connect --env dev --role admin

# Run a tool directly from CLI (kwargs map to tool args)
grafana-sdk run list_dashboards --env prod --role viewer --tags production
grafana-sdk run get_dashboard --uid abc123 --env dev
grafana-sdk run silence_alert --env prod --role editor \
                              --matcher '{job="api"}' --duration-minutes 30 \
                              --comment "scheduled maintenance"

# Interactive REPL
grafana-sdk shell --env dev --role editor

# Generate a starter .grafana-mcp.toml
grafana-sdk init

# List every tool with its signature
grafana-sdk list-tools

# Print version
grafana-sdk --version
```

### `shell` — interactive REPL

```python
$ grafana-sdk shell --env dev --role editor
Bifröst SDK shell — env: dev, role: editor
Type help() for tool list, exit() to quit.

>>> dashboards = await g.list_dashboards(tags=["production"])
>>> len(dashboards)
12
>>> dashboards[0].title
'API Health'
>>> async with g.as_role("admin") as admin_g:
...     users = await admin_g.list_users()
>>> len(users)
47
>>> exit()
```

The shell is built on `ptpython` with a pre-bound `g` and `mcp` in scope and all the SDK schemas imported. Tab completion works on tool names and parameters.

## Error handling

Every SDK call can raise:

- **`PermissionError`** — role is below the tool's minimum
- **`GrafanaError`** — Grafana returned 4xx/5xx after retries (subclass with `.status_code` and `.response_body`)
- **`ConnectionError`** — couldn't reach Grafana at all (proxy, DNS, TLS)
- **`ValidationError`** — Grafana returned a body that didn't match the Pydantic schema (Grafana version mismatch)

Wrap in try/except as needed. The CLI prints errors to stderr and exits non-zero.

## Logging

By default the SDK is silent. Enable structured logging with:

```python
from grafana_mcp_sdk import configure_logging
configure_logging(level="INFO", fmt="console")
```

Same `structlog` setup as the server, same auth-header redaction. In CI, set `fmt="json"` for log shippers.

## Tests

```bash
make sdk-test
```

The SDK tests use `respx` to mock Grafana the same way the core tests do. There's a small set of integration tests that hit a live Grafana via the demo profile — gated behind `pytest -m integration` so they don't run by default.
