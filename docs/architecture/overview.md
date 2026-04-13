# System Overview

Bifröst is small on purpose. Three packages, one protocol, two transports, three environments, three roles. Everything else is convention.

## High-level shape

```
┌────────────────────────────────────────────────────────────────────────┐
│                              Bifröst                                    │
└────────────────────────────────────────────────────────────────────────┘

  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
  │  React UI      │    │  Python SDK    │    │  VSCode MCP    │
  │  (browser)     │    │  (notebooks)   │    │  Extension     │
  └───────┬────────┘    └───────┬────────┘    └───────┬────────┘
          │  SSE                │  HTTP               │  SSE
          └─────────────────────┼─────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────────┐
                  │   packages/core (Python)    │
                  │  ─────────────────────────  │
                  │   FastAPI + MCP SDK         │
                  │   Role Enforcement          │
                  │   Pydantic Tool Schemas     │
                  │   structlog · tenacity      │
                  └──────────────┬──────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
        ┌──────────┐       ┌──────────┐       ┌──────────┐
        │ env: dev │       │ env: perf│       │ env: prod│
        │  v/e/a   │       │  v/e/a   │       │  v/e/a   │
        └─────┬────┘       └─────┬────┘       └─────┬────┘
              │                  │                  │
              ▼                  ▼                  ▼
        ┌─────────────────────────────────────────────────┐
        │             Grafana HTTP API (9.x – 12.x)        │
        └─────────────────────────────────────────────────┘
```

## The three packages

### `packages/core` — the MCP server

Pure Python, runs on `python>=3.11`. Built on:

- **`mcp[cli]`** — the official Anthropic MCP Python SDK. Provides the `@mcp.tool()` decorator, the JSON-RPC layer, and the SSE/streamable-HTTP transport implementations.
- **FastAPI + uvicorn** — the HTTP layer that hosts the MCP transports and an extra `/healthz` endpoint for ops.
- **`httpx[http2]`** — async Grafana HTTP client with HTTP/2, connection pooling, and per-environment-per-role pool reuse.
- **`pydantic-settings`** — 12-factor config loading.
- **`structlog`** — structured logging with auth-header redaction.
- **`tenacity`** — exponential backoff retry on Grafana 429 / 5xx.

The core package owns:

- The **Settings** model and `.env` loading
- The **GrafanaClient** (one instance per env+role pair, pooled)
- The **role enforcement middleware** (the `TOOL_MINIMUM_ROLE` table)
- All ~20 MCP tools, each as a typed async function
- The CLI: `grafana-mcp serve`, `validate-config`, `list-tools`, `health`

### `packages/sdk` — the Python developer SDK

A separate distributable so you can `pip install grafana-mcp-sdk` without dragging the server in. Built on the same `httpx` client and tool schemas as core, but **does not run a server**. It speaks directly to Grafana the same way the server does — same role model, same retry, same logging — packaged as an idiomatic Python library.

Key trick: the SDK and core share a *single source of truth* for tool input/output schemas (a `packages/_schemas/` directory both packages depend on via `uv` workspaces). When you add a tool to core, the SDK gets it for free.

### `packages/ui` — the React chat app

Vite + React 19 + TypeScript 5.5 + Tailwind v4. Connects to a running core server over **SSE only**. Three main features:

- **Connection Config** — three environment cards, role selector, transport config
- **AI Chat** — Claude/OpenAI wired to live MCP tools, streaming responses, tool-call cards
- **Resource Explorer** — live tree of folders → dashboards → panels, fed by MCP tool calls

## The two transports

| Mode | Wire format | Best for | Ports (default) |
|---|---|---|---|
| `sse` | Server-Sent Events over HTTP | VSCode + browser UI — anything interactive | `8765` (dev), `8766` (prod admin) |
| `http` | Streamable HTTP per MCP spec | SDK + CI — anything pipeline-shaped | `8769` (dev) |

Both expose the **identical tool surface**. You can run both at the same time, on different ports, against the same backend — many teams do exactly that to give the UI an SSE endpoint and the SDK an HTTP one.

See [Transports](transports.md) for the protocol-level details.

## The three environments

`dev`, `perf`, `prod` — named, not freeform. The literal type forces consistency:

```python
class GrafanaEnvironment(BaseModel):
    name: Literal["dev", "perf", "prod"]
    base_url: AnyHttpUrl
    service_accounts: ServiceAccountSet
    tls_verify: bool = True
    timeout_seconds: float = 30.0
    rate_limit_rps: float = 10.0
```

Each is independently configured. You don't have to define all three — but `active_environment` must reference one you *did* define. Settings validation enforces this on startup.

See [Environment Model](environments.md) for the detailed semantics.

## The three roles

`viewer`, `editor`, `admin` — mapped 1:1 to Grafana RBAC roles. Each environment holds three Grafana service-account tokens, one per role.

```python
class ServiceAccountSet(BaseModel):
    viewer: SecretStr
    editor: SecretStr
    admin:  SecretStr
```

The MCP server picks the right token for every tool call based on the active role plus the per-tool minimum role:

```python
ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "admin": 2}

TOOL_MINIMUM_ROLE: dict[str, Literal["viewer", "editor", "admin"]] = {
    "silence_alert":         "editor",
    "list_users":            "admin",
    "list_service_accounts": "admin",
    # everything else defaults to "viewer"
}
```

If the active role can't satisfy the minimum, Bifröst raises `PermissionError` *before* the HTTP call leaves the process. No silent escalation, no token mixing.

See [Role Model](role-model.md) for the full hierarchy and the rationale.

## Request lifecycle

1. **Client** sends an MCP `tools/call` over SSE or streamable HTTP.
2. **Core** parses the call, looks up the tool, validates the args against the Pydantic input schema.
3. **Role enforcement** middleware checks `TOOL_MINIMUM_ROLE[tool] <= active_role`. Fails fast if not.
4. The tool function pulls the **`GrafanaClient`** for the active env+role from the pool.
5. The client makes the HTTP call to Grafana with the right service-account token. Retries on 429/5xx with exponential backoff. Rate-limited via `asyncio.Semaphore`.
6. The Grafana response is parsed into a Pydantic output model.
7. Core serializes the output back to the MCP client.
8. **Every step is logged** via `structlog` with auth headers redacted.

End to end, a typical tool call lands a response in 30-100 ms (assuming Grafana is on the same network).

## Why this shape?

- **MCP first.** Once you commit to MCP, you get VSCode, Claude Code, Cursor, Cline, and every future agent for free. Nobody has to write a Bifröst-specific integration.
- **Role-aware tokens.** The single biggest risk in "let the LLM drive Grafana" is letting the LLM run with admin tokens by accident. Three explicit tokens, one per role, with a fail-fast minimum table — that's the smallest possible safety net.
- **Three named environments.** "dev / perf / prod" matches how every observability team actually thinks. Freeform env names would let teams invent `dev2`, `dev-temp`, `gopal-laptop` and the discipline would rot in a quarter.
- **Two transports, one tool surface.** SSE is great for UIs, streamable HTTP is great for SDKs. Forcing one would alienate one of them.
- **Pydantic everywhere.** The contract is the schema. The schema is the contract.
