# Installation

Bifröst is a Python workspace (`packages/core` + `packages/sdk`) plus a React app (`packages/ui`). You can install it three ways: Docker (recommended), manual local install with `uv` + `pnpm`, or pip-only for the SDK alone.

## Prerequisites

- **Python 3.11+** — verify with `python --version`. The core server uses modern typing features that require 3.11 minimum.
- **[uv](https://docs.astral.sh/uv/)** — the workspace is built around `uv sync`. Install with `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **Node.js 20+** + **pnpm 9+** — only needed if you're running the React UI locally.
- **Grafana 9.x – 12.x** — OSS or Enterprise, reachable on the network. The demo profile boots its own Grafana so you can skip this for the first run.
- **Three Grafana service-account tokens per environment** — one each for `viewer`, `editor`, `admin`. See [first-run](first-run.md#generating-service-account-tokens).
- **~400 MB disk** — Python wheels + node_modules + the docker images.

## Option 1 — Docker *(recommended)*

```bash
git clone https://github.com/gpadidala/bifrost.git
cd bifrost
./demo-run.sh
```

The demo script:

1. Boots a pre-seeded Grafana on `:3000` (admin/admin)
2. Auto-creates `bifrost-viewer`, `bifrost-editor`, `bifrost-admin` service accounts
3. Writes their tokens into a temporary `.env`
4. Starts the MCP server on `:8765` (SSE) and `:8766` (HTTP)
5. Starts the React UI on `:5173`

Open **<http://localhost:5173>** and you should see all three environment cards (only `dev` connected). See [Docker deployment](../deployment/docker.md) for production configs.

## Option 2 — Manual local install (full workspace)

```bash
git clone https://github.com/gpadidala/bifrost.git
cd bifrost

# Python workspace — installs core + sdk + dev tools
uv sync --all-extras

# UI — only needed if you want the chat app
pnpm --filter ./packages/ui install

# Configure
cp .env.example .env
$EDITOR .env       # set your Grafana URLs and 9 service-account tokens

# Validate the config without booting
uv run grafana-mcp validate-config

# Start the MCP server (SSE for the UI)
uv run grafana-mcp serve --transport sse --env dev --role viewer --port 8765
```

Then in another terminal:

```bash
pnpm --filter ./packages/ui dev   # → http://localhost:5173
```

Continue with the [Quick Start](quick-start.md).

## Option 3 — SDK only (`pip install`)

If you only want the Python SDK for notebooks or CI scripts and don't need the server or UI:

```bash
pip install grafana-mcp-sdk
# or
uv add grafana-mcp-sdk
```

Then drop a `.grafana-mcp.toml` in your project root or `~/.config/grafana-mcp/config.toml` and you're done — see [SDK reference](../api/sdk-reference.md).

## Verifying the install

```bash
# Core server CLI is on PATH
grafana-mcp --version
grafana-mcp list-tools           # should print ~20 tools

# SDK CLI is on PATH
grafana-sdk --version
grafana-sdk connect --env dev    # round-trips to Grafana with the viewer token
```

If `grafana-mcp` isn't on your PATH, your `uv sync` may have created a `.venv` you haven't activated. Use `uv run grafana-mcp ...` or `source .venv/bin/activate`.

## Troubleshooting

Install failures are almost always one of: wrong Python version, corporate proxy, or missing C build tools for `httpx[http2]`. See [Troubleshooting → install issues](../guides/troubleshooting.md#install-issues) for common fixes.
