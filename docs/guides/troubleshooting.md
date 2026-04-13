# Troubleshooting

The top issues people hit, in rough order of frequency, with their fixes. If yours isn't here, [open an issue](../../.github/ISSUE_TEMPLATE/bug_report.md) with the matching `grafana-mcp` log lines (auth headers are auto-redacted).

## Install issues

### `uv: command not found`

You don't have `uv` installed. Get it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then close and reopen your terminal so the new PATH entry takes effect.

### `pnpm: command not found`

`pnpm` is bundled with Node 20+ via corepack:

```bash
corepack enable
```

If that doesn't work, install via your package manager (`brew install pnpm`, `npm install -g pnpm`).

### `httpx[http2]` build failure on `pip install`

`httpx[http2]` pulls in `h2` and `hpack`, which sometimes need wheels that aren't built for your Python+OS combo. The fix is usually to upgrade pip:

```bash
pip install --upgrade pip
```

If that doesn't work, install build tools (Linux: `build-essential`, macOS: `xcode-select --install`).

### Corporate proxy SSL inspection

`uv sync` or `pnpm install` fails with SSL cert errors. Set proxy env vars and (carefully) trust your corp CA:

```bash
export HTTP_PROXY=http://proxy.corp.example.com:8080
export HTTPS_PROXY=http://proxy.corp.example.com:8080
export NO_PROXY=localhost,127.0.0.1
```

For pip specifically, you can also configure it once:

```bash
pip config set global.cert /path/to/corp-ca.crt
```

For docker builds in this environment, see [Corporate networks (SSL proxy)](../deployment/docker.md#corporate-networks-ssl-proxy).

## Config & connection issues

### `validate-config` shows `✗ 401` for one role

That token is wrong, expired, or revoked. In Grafana:

1. **Administration → Service accounts**
2. Find the matching `bifrost-<role>` account
3. Either generate a new token or check the role assignment hasn't been downgraded
4. Update the token in `.env`
5. Re-run `grafana-mcp validate-config`

If all three roles in one env show 401, the URL is probably wrong (different Grafana instance) or the org is wrong (token belongs to a different org). Double-check `BASE_URL` and the org of each service account.

### `validate-config` shows `✗ connection refused`

Grafana isn't running on the URL you configured, or there's a network issue (firewall, VPN, DNS).

```bash
# From the same machine that runs Bifröst:
curl -fsS https://grafana.company.com/api/health
```

If that fails too, the problem is upstream — fix the network before fixing Bifröst.

### `Pydantic validation error` on startup

Usually missing required fields. The most common variants:

```
ValidationError: 1 validation error for Settings
environments.dev.service_accounts.editor
  Field required
```

You forgot one of the three tokens for an env block. **All three are required** even if you don't plan to use the higher roles. Add the missing token (or the placeholder line from `.env.example`).

```
ValidationError: 1 validation error for Settings
active_environment
  Input should be 'dev', 'perf' or 'prod'
```

Your `GRAFANA_MCP_ACTIVE_ENVIRONMENT` is something other than the three literal values. Pick one of `dev` / `perf` / `prod`.

```
ValidationError: 1 validation error for Settings
environments.dev.base_url
  Input should be a valid URL
```

Trailing whitespace or a missing scheme. `http://localhost:3000`, not `localhost:3000`.

## Server issues

### Server starts but `/healthz` returns 503

The server booted but the active env+role can't reach Grafana. Check the startup logs for the `grafana.health_check` event. The fix is one of:

- Wrong URL → fix `.env`
- Wrong token → see [validate-config 401](#validate-config-shows--401-for-one-role)
- Grafana down → fix Grafana

### `RuntimeError: SSE transport requires asyncio`

You're running on Windows with the wrong event loop policy. uvicorn picks the right one automatically, but if you boot from a non-uvicorn entry point you need:

```python
import asyncio, sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

The shipped `grafana-mcp serve` does this for you. Only relevant if you're embedding the server in your own code.

### Tool calls fail with `RateLimitError`

The per-env semaphore is full and the call timed out waiting. Either:

- The LLM is making too many parallel tool calls (some Claude conversations fan out 20+ at once)
- Another process is hammering the same Bifröst instance

Bump `RATE_LIMIT_RPS` for the env (default 10):

```env
GRAFANA_MCP_ENVIRONMENTS__PROD__RATE_LIMIT_RPS=25
```

Watch your Grafana for the load — Bifröst's rate limit is **client-side**, not Grafana's. Grafana itself can handle more, but you may not want to.

## UI issues

### UI shows "Disconnected" but the server is running

Check the URL the UI is trying to use. Open browser devtools → Network → look for the SSE connection. The URL should match what `grafana-mcp serve` is bound to. If the UI is using `http://localhost:8765` and the server is bound to `127.0.0.1:8765`, the browser can't reach it. Restart the server with `--host 0.0.0.0`.

### "CORS error" in browser console

The UI app is on `http://localhost:5173` and the server is on `http://localhost:8765`, which is a CORS-relevant cross-origin scenario. The shipped `grafana-mcp serve` configures CORS to allow `localhost:5173` by default. If you've changed the UI port, set:

```env
GRAFANA_MCP_CORS_ORIGINS=http://localhost:5173,http://localhost:3001
```

(Note: this is a server-side setting, not a UI one.)

### Tool-call card stuck on "Pending"

The MCP request was sent but no response came back. Three causes:

1. The server crashed mid-call. Check the server terminal — there should be a stack trace.
2. The Grafana call is just slow (e.g., `query_datasource` against a big Loki). Bump `TIMEOUT_SECONDS`.
3. A reverse proxy in the middle is buffering the SSE stream. See [reverse proxy notes](../deployment/docker.md#reverse-proxy-notes-sse).

### "Encryption passphrase incorrect" on UI reload

You enabled localStorage encryption and forgot the passphrase. There's no recovery. Open browser devtools → Application → Local Storage → clear the entries for the Bifröst origin and start over with a fresh config.

## SDK issues

### `ConfigError: no .grafana-mcp.toml found`

The SDK looked in the current dir, every parent dir, and `~/.config/grafana-mcp/` and didn't find a TOML. Either:

- Create one with `grafana-sdk init`
- Pass explicit kwargs to `GrafanaMCP(...)`
- Set the `GRAFANA_MCP_*` env vars

### `${PROD_VIEWER_TOKEN}` literal showing up as the token value

The `.grafana-mcp.toml` has env-var interpolation, but the env var isn't set. The SDK refuses to silently use the literal `${...}` string. Set the env var or hard-code the token in the TOML (don't do this for prod).

### `asyncio` warnings when using `mcp.sync()` in a notebook

Some notebook kernels set up their own event loop policy that conflicts with the SDK's sync wrapper. Use `mcp.connect()` and `await` instead:

```python
async with mcp.connect() as g:
    dashboards = await g.list_dashboards()
```

Modern Jupyter and JupyterLab support top-level `await` — this is the cleaner pattern.

## Role / RBAC issues

### `PermissionError: Tool 'X' requires role 'editor', got 'viewer'`

Working as intended. Either:

- Restart the server with `--role editor` (or higher)
- Use the SDK's `as_role` context manager: `async with g.as_role("editor") as editor_g:`
- The LLM should ask the user before retrying with a higher role

### Server started with `--role admin` but admin tools still fail

The admin token in `.env` doesn't actually have the Admin role in Grafana. Open the service-account page in Grafana and check the role. Bifröst's role labels are *names*, not *enforcement* — Grafana itself enforces what the token can do.

### "I want a fourth role"

Don't. See [Role Model → Adding a new role?](../architecture/role-model.md#adding-a-new-role).

## Logging issues

### Logs are too noisy

Bump the level:

```env
GRAFANA_MCP_LOG_LEVEL=WARNING
```

Or filter at the log shipper if you only care about a subset of events.

### Logs are missing context

Bifröst uses `structlog.contextvars` to attach env, role, and tool to every log line in a request. If your custom processors strip context vars, you lose that. Use the default `configure_logging` and add processors to it rather than replacing it.

### Auth tokens leaking into logs

This should never happen — `redact_auth_headers` runs as a `structlog` processor on every log line. If you see a `glsa_...` value in your logs, please [open a bug report](../../.github/ISSUE_TEMPLATE/bug_report.md) immediately. Include the offending log line with the token redacted by hand.

## "It worked yesterday, broken today"

In this order:

1. **Did Grafana update?** Check `grafana-mcp health` for the version. If a version bump landed, some Grafana API responses may have changed shape — update Bifröst (`uv sync` to pull the latest pydantic schemas).
2. **Did your tokens rotate?** Run `grafana-mcp validate-config`. A common cause is a Vault-driven rotation that wasn't propagated to Bifröst's `.env`.
3. **Did the network change?** Corporate VPN, DNS, proxy — all common culprits. Try `curl` from the same host.
4. **Did you change the active env?** A `dev/admin` token won't work against `prod` no matter what.
5. **Has anything been deployed?** `git log` on the Bifröst repo since yesterday. New tools or schema changes can shift behavior.

## Where to ask for help

1. Check this page first
2. Search [open + closed issues](../../../issues?q=is%3Aissue) for similar reports
3. [File a new bug report](../../.github/ISSUE_TEMPLATE/bug_report.md) with:
   - Bifröst version (`grafana-mcp --version`)
   - Grafana version (`curl https://grafana.company.com/api/health`)
   - Active env + role
   - Transport mode
   - The relevant log lines (auth headers auto-redacted)
   - What you expected vs what happened
