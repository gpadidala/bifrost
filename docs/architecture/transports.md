# Transports — SSE vs Streamable HTTP

Bifröst supports two MCP transport modes from the same codebase. You pick one at startup with `--transport sse` or `--transport http`. Both expose the **identical tool surface** — the only difference is the wire protocol.

## TL;DR

| | SSE | Streamable HTTP |
|---|---|---|
| **Best for** | VSCode, browser UI, anything interactive | Python SDK, CI/CD, batch jobs, notebooks |
| **Connection** | One long-lived HTTP connection per client | One HTTP request per tool call |
| **Wire format** | Server-Sent Events (`text/event-stream`) | JSON over HTTP, optionally streamed |
| **Proxy-friendly?** | Sometimes — corporate proxies hate long-lived connections | Yes — looks like normal HTTP |
| **Multi-client?** | Yes — many clients can connect to one server | Yes — stateless, scales trivially |
| **Default port (Bifröst)** | `8765` | `8769` |

If you don't know which one to pick, the answer is **SSE for interactive use, HTTP for everything else**. You can run both at the same time on different ports.

## SSE transport

Server-Sent Events are a one-way streaming protocol over HTTP. The MCP spec uses SSE bi-directionally by combining a long-lived `GET /sse` for server→client events with a `POST /messages` for client→server commands. The two are correlated by a session ID.

### How clients connect

```
GET /mcp/sse HTTP/1.1
Accept: text/event-stream
```

The server responds with:

```
event: endpoint
data: /mcp/messages?session_id=abc123

event: tool
data: {"name":"list_dashboards","input_schema":{...},...}
...
```

The client then sends tool calls as POSTs:

```
POST /mcp/messages?session_id=abc123 HTTP/1.1
Content-Type: application/json

{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_dashboards","arguments":{}}}
```

And the result comes back as an SSE event on the original stream.

### When SSE is the right choice

- **VSCode MCP extension** — VSCode opens one SSE connection per server in `mcp.json` and keeps it warm.
- **Browser chat UI** — Bifröst's React app uses `EventSource` for the SSE stream. Tool-call cards animate in as events arrive.
- **Multi-tool conversations** — when you expect 5+ tool calls in a single LLM turn, the warm connection avoids per-call TLS handshake overhead.

### When SSE is wrong

- **Behind a corporate proxy** that buffers responses or kills idle HTTP connections — the SSE stream will hang.
- **Serverless deployment** — Lambda / Cloud Run idle timeouts kill long-lived SSE connections.
- **One-shot CI calls** — opening an SSE session for a single tool call is overkill.

For these, use streamable HTTP.

## Streamable HTTP transport

Streamable HTTP is the newer MCP transport (introduced in MCP spec 0.6). Every tool call is a single `POST` that streams its response back. No long-lived connection, no session ID, no SSE quirks.

### How clients connect

```
POST /mcp/messages HTTP/1.1
Content-Type: application/json

{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_dashboards","arguments":{}}}
```

The server responds with:

```
HTTP/1.1 200 OK
Content-Type: application/json
Transfer-Encoding: chunked

{"jsonrpc":"2.0","result":{"content":[...]}}
```

For long-running tools, the server can stream chunks as they're ready (`Transfer-Encoding: chunked`). For fast tools, it just returns one JSON object.

### When streamable HTTP is the right choice

- **Python SDK** — `GrafanaMCP.from_env()` uses streamable HTTP under the hood. One call, one HTTP request, done.
- **CI / cron / batch jobs** — pipeline scripts that fire one or two calls and exit.
- **Notebooks** — Jupyter cells call `g.list_dashboards()` and want a clean response, not a session.
- **Behind hostile proxies** — looks like a normal HTTP API call. Works through every proxy that allows JSON POSTs.
- **Horizontally scaled deployments** — stateless, so you can put a load balancer in front and round-robin requests.

### When streamable HTTP is wrong

- **Browser UIs** that want progressive rendering of mid-stream tool-call cards. SSE handles that more naturally.
- **VSCode MCP extension** — currently only SSE is supported by the extension.

## Running both at the same time

A common Bifröst deployment pattern is to run **two server processes** against the same backend config:

```bash
# Terminal 1 — SSE for the UI + VSCode
uv run grafana-mcp serve --transport sse  --env dev --role viewer --port 8765

# Terminal 2 — streamable HTTP for the SDK + CI
uv run grafana-mcp serve --transport http --env dev --role viewer --port 8769
```

Both processes load the same `.env`, both pool connections to the same Grafana, both enforce roles the same way. The only thing that differs is the wire protocol.

In docker-compose this is two `bifrost-core` services with different `--transport` and `--port` flags — see [docker-compose.yml](../../docker-compose.yml).

## Health checks

Both transports expose `/healthz` (FastAPI route, not MCP):

```bash
curl http://localhost:8765/healthz
{"status":"ok","environment":"dev","role":"viewer","grafana":{"latency_ms":12}}
```

This is what `docker compose` and `kubectl` use for liveness/readiness probes. It does *not* require an MCP session.

## Picking ports

The defaults are picked to be memorable, not prescriptive:

| Port | Convention |
|---|---|
| `8765` | dev / SSE / viewer |
| `8766` | prod / SSE / admin |
| `8767` | dev / SSE / editor |
| `8768` | perf / SSE / viewer |
| `8769` | dev / streamable HTTP / any role |

You're free to use any port. Update `.vscode/mcp.json` to match if you change them.
