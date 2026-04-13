# Environment Model

Bifröst supports **exactly three named environments**: `dev`, `perf`, `prod`. They are not freeform strings — they're a literal type baked into the schema.

## Why three named environments?

Every observability team alive thinks in roughly the same three buckets:

- **`dev`** — your laptop, your sandbox, your cattle Grafana. Mistakes are cheap.
- **`perf`** — staging / pre-prod / load-test cluster. Mistakes are visible.
- **`prod`** — the one that pages the on-call. Mistakes wake people up.

By naming them up front and refusing to support arbitrary environment names, Bifröst forces you to map your actual clusters to the same three buckets every other Bifröst user has. This pays off in three ways:

1. **The UI is always the same.** Three cards, same labels, every install.
2. **Tooling assumes the names.** `.vscode/mcp.json`, the SDK CLI, the LLM system prompt — all hard-code `dev | perf | prod`.
3. **Discipline doesn't rot.** You can't invent `dev2`, `temp-cluster`, or `gopal-laptop` and have it linger for two years.

If you only have two environments, just don't define `perf`. If you have five, the right answer is to make Bifröst-aware tooling pick the closest of the three, not to add a fourth.

## The Pydantic model

```python
class GrafanaEnvironment(BaseModel):
    name: Literal["dev", "perf", "prod"]
    base_url: AnyHttpUrl
    service_accounts: ServiceAccountSet
    tls_verify: bool = True
    timeout_seconds: float = 30.0
    rate_limit_rps: float = 10.0
```

| Field | Description |
|---|---|
| `name` | Literal — `dev`, `perf`, or `prod`. Anything else is a Pydantic error at startup. |
| `base_url` | Grafana URL with no trailing slash. `http://localhost:3000` for dev, `https://grafana.company.com` for prod. |
| `service_accounts` | Three secret tokens — `viewer`, `editor`, `admin`. See [Role Model](role-model.md). |
| `tls_verify` | `false` only for self-signed dev clusters. **Never `false` in prod.** |
| `timeout_seconds` | Per-request HTTP timeout. 30s is enough for almost everything; bump for slow `query_datasource` calls against Loki/Mimir. |
| `rate_limit_rps` | Max in-flight requests per second across all roles for this env. Implemented via `asyncio.Semaphore`. Tune up for dev (20), down for prod (10) if you share Grafana with humans. |

## How environments are picked per request

In order of precedence:

1. **Per-call override** in the MCP tool call context (`environment` parameter on the tool input). Lets one tool call hit a different env than the server default — useful for cross-env comparisons.
2. **Server default** from `--env` CLI flag or `GRAFANA_MCP_ACTIVE_ENVIRONMENT` env var.

Unlike roles, the env can be changed freely on a per-call basis — there's no hierarchy and no "ceiling" to enforce. The only constraint is that the requested env must exist in `settings.environments`. Asking for `dev` from a server that only loaded `prod` raises an error.

## Connection pooling per env+role

The core server keeps **one `httpx.AsyncClient` per (env, role) pair**, pooled and reused across requests. With three envs and three roles you get up to nine pooled clients. Each client has its own:

- Base URL (from the env)
- Bearer token (from the role)
- TLS verify setting (from the env)
- Timeout (from the env)
- HTTP/2 connection pool (httpx default)

The pool is built lazily on first use of each pair and torn down on server shutdown. Switching env or role mid-session is free — you're just looking up a different client from the dict.

## Cross-environment tools

Some tools accept an `environment` argument to query a specific env regardless of the server default. For example:

```python
@mcp.tool()
async def health_check(
    environment: Literal["dev", "perf", "prod"] | None = None,
) -> HealthStatus:
    """Ping Grafana and return health status. Defaults to active env."""
    env_name = environment or settings.active_environment
    ...
```

This is the only sanctioned way to do cross-env work from one tool call. Don't smuggle env names into other parameters — keep them in the explicit `environment` arg so the LLM and the audit log can both see it.

## Switching the active environment from the UI

The React UI shows the active env in the header as a segmented control: **DEV · PERF · PROD**. Clicking a different env:

1. Updates the Zustand `connectionStore.activeEnvironment`
2. Re-issues the MCP `initialize` handshake with the new env in the context
3. Re-fetches the resource explorer tree from the new env
4. Adds a "switched to PERF" system message to the chat

The chat history is preserved across env switches, but the LLM is informed about the switch in its next system prompt update so it doesn't get confused about which env it's looking at.

## Switching the active environment from the SDK

```python
async with mcp.connect() as g:
    dev_dashboards = await g.list_dashboards()           # active env from config

    async with g.as_environment("prod") as prod_g:
        prod_dashboards = await prod_g.list_dashboards() # explicit prod
```

The `as_environment` context manager swaps the env for the duration of the `with` block, then snaps back. It's the symmetric form of `as_role` from [Role Model](role-model.md#enforcement).

## What if I have more than three Grafana clusters?

Common case: separate clusters for `eu-west`, `us-east`, `ap-southeast`. Two acceptable patterns:

1. **One Bifröst per region.** Run three Bifröst servers, one against each region. Each thinks of itself as having one `prod` env. The MCP client (VSCode, agent) picks which Bifröst to connect to.
2. **Region in the env name.** Set `prod` to `eu-west` and run separate Bifröst processes for the others, each with its own port and label in `mcp.json`. Less elegant but only one config file.

Pattern 1 scales better. Pattern 2 is fine for two or three clusters.
