# Docker Deployment

Bifröst ships with a multi-stage `Dockerfile` that builds two images out of one workspace:

- **`bifrost-core`** — the Python MCP server (target: `core`)
- **`bifrost-ui`** — the React app served by nginx-alpine (target: `ui`)

Plus an optional **`grafana-demo`** service in the compose file (profile: `demo`) that boots a pre-seeded Grafana so you can try Bifröst without your own.

## Quick start

```bash
git clone https://github.com/gpadidala/bifrost.git
cd bifrost

# Default profile — core + UI only, you bring your own Grafana via .env
cp .env.example .env
$EDITOR .env
docker compose up -d --build

# Demo profile — adds a pre-seeded Grafana on :3000 with auto-generated tokens
docker compose --profile demo up -d --build
```

| URL | What |
|---|---|
| <http://localhost:5173> | Bifröst UI |
| <http://localhost:8765/mcp/sse> | SSE transport (UI + VSCode) |
| <http://localhost:8766/mcp/sse> | (default empty — use for prod admin server) |
| <http://localhost:3000> | Demo Grafana (only with `--profile demo`) |

## The Dockerfile

It's a multi-stage build with three notable targets:

```dockerfile
# ── stage 1: python builder ─────────────────────────────────────
FROM python:3.13-slim AS python-builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY packages/sdk/pyproject.toml  packages/sdk/
RUN pip install uv && uv sync --frozen --no-dev
COPY packages/core/src packages/core/src
COPY packages/sdk/src  packages/sdk/src

# ── stage 2: core runtime ───────────────────────────────────────
FROM python:3.13-slim AS core
WORKDIR /app
COPY --from=python-builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8765
HEALTHCHECK --interval=15s --timeout=3s CMD curl -fsS http://localhost:8765/healthz || exit 1
ENTRYPOINT ["grafana-mcp"]
CMD ["serve", "--transport", "sse", "--host", "0.0.0.0", "--port", "8765"]

# ── stage 3: ui builder ─────────────────────────────────────────
FROM node:20-alpine AS ui-builder
WORKDIR /app
COPY packages/ui/package.json packages/ui/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY packages/ui/ ./
RUN pnpm build

# ── stage 4: ui runtime ─────────────────────────────────────────
FROM nginx:1.27-alpine AS ui
COPY --from=ui-builder /app/dist /usr/share/nginx/html
COPY packages/ui/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

The `core` target installs only runtime deps (no `pytest`, no `ruff`) and stays around 180 MB. The `ui` target is plain nginx-alpine + the built static files, ~30 MB.

## docker-compose.yml

The compose file ships three services:

```yaml
services:
  bifrost-core:    # MCP server, port 8765 (SSE), 8766 (HTTP)
  bifrost-ui:      # Nginx serving the React app on port 5173 → 80
  grafana-demo:    # Pre-seeded Grafana on 3000 (profile: demo only)
```

The full file is in [docker-compose.yml](../../docker-compose.yml). Notable bits:

- `bifrost-core` reads `.env` directly via `env_file` — no env-var duplication
- A `healthcheck` on `bifrost-core` polls `/healthz` every 15s; `bifrost-ui` waits on it via `depends_on: condition: service_healthy`
- `grafana-demo` is gated behind `profiles: ["demo"]` so it doesn't boot in production
- A named volume `grafana-demo-data` persists the demo Grafana's SQLite

## Multi-instance pattern (one per role)

A common production deployment is **one Bifröst process per (env, role)** so each container has the smallest privilege envelope. Use a compose override:

```yaml
# docker-compose.prod.yml
services:
  bifrost-prod-viewer:
    extends:
      file: docker-compose.yml
      service: bifrost-core
    environment:
      GRAFANA_MCP_ACTIVE_ENVIRONMENT: prod
      GRAFANA_MCP_ACTIVE_ROLE: viewer
      GRAFANA_MCP_TRANSPORT__PORT: 8765
    ports:
      - "8765:8765"

  bifrost-prod-editor:
    extends:
      file: docker-compose.yml
      service: bifrost-core
    environment:
      GRAFANA_MCP_ACTIVE_ENVIRONMENT: prod
      GRAFANA_MCP_ACTIVE_ROLE: editor
      GRAFANA_MCP_TRANSPORT__PORT: 8767
    ports:
      - "8767:8767"

  bifrost-prod-admin:
    extends:
      file: docker-compose.yml
      service: bifrost-core
    environment:
      GRAFANA_MCP_ACTIVE_ENVIRONMENT: prod
      GRAFANA_MCP_ACTIVE_ROLE: admin
      GRAFANA_MCP_TRANSPORT__PORT: 8766
    ports:
      - "8766:8766"
```

Boot with:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Corporate networks (SSL proxy)

If your network does MITM SSL inspection and `uv sync` or `pnpm install` fails inside the build:

```bash
export HTTP_PROXY=http://proxy.corp.example.com:8080
export HTTPS_PROXY=http://proxy.corp.example.com:8080
export NO_PROXY=localhost,127.0.0.1
docker compose build
```

Compose forwards these as `--build-arg` and the Dockerfile installs them as env vars in the builder stages. The `python-builder` stage trusts the `pip` index and `uv` index based on the proxy CA bundle, which the corp typically injects via a base image override.

If you also need a custom CA bundle:

```dockerfile
ARG CA_BUNDLE
RUN if [ -n "$CA_BUNDLE" ]; then \
      echo "$CA_BUNDLE" > /usr/local/share/ca-certificates/corp-ca.crt && \
      update-ca-certificates ; \
    fi
```

Pass the cert via `--build-arg CA_BUNDLE="$(cat corp-ca.crt)"`.

## Production checklist

- ✅ Use `--profile` to disable `grafana-demo` in prod (default profile already excludes it)
- ✅ Set `GRAFANA_MCP_LOG_FORMAT=json` so log shippers can parse
- ✅ Run a separate container per (env, role) so the privilege envelope is obvious from `docker ps`
- ✅ Mount `.env` as a Docker secret rather than embedding tokens in compose files
- ✅ Front the SSE port with a reverse proxy that supports long-lived HTTP connections (nginx with `proxy_buffering off`, Traefik, Caddy)
- ✅ Set `bifrost-core` resource limits — 256 MB memory, 0.5 CPU is enough for 50 concurrent tool calls
- ✅ Pin image tags (`gpadidala/bifrost-core:1.3.0`), don't rely on `:latest` in prod
- ✅ Make sure the host's clock is correct — Grafana service-account tokens are sensitive to clock skew on the TLS handshake

## Reverse proxy notes (SSE)

Nginx has SSE-killer defaults. Minimal working config:

```nginx
location /mcp/ {
    proxy_pass http://bifrost-core:8765;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;          # critical for SSE
    proxy_read_timeout 24h;       # long-lived connections
    chunked_transfer_encoding off;
}
```

For Traefik, set the middleware:

```yaml
http:
  middlewares:
    bifrost-sse:
      buffering:
        maxRequestBodyBytes: 0
        maxResponseBodyBytes: 0
```

## Image size & build time

| Image | Size | Cold build | Warm build |
|---|---|---|---|
| `bifrost-core` | ~180 MB | ~90s | ~12s |
| `bifrost-ui` | ~30 MB | ~60s | ~8s |

Cold = no Docker layer cache. Warm = changing one source file. The `uv sync` and `pnpm install` layers are cached on the lockfiles, so source-only changes rebuild fast.

## Related

- [VSCode integration](vscode.md)
- [CI/CD integration](ci-cd.md)
- [Configuration reference](../getting-started/configuration.md)
