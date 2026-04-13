# ─────────────────────────────────────────────────────────────────
#  Bifröst — multi-stage Dockerfile
#
#  Targets:
#    core  — Python MCP server (grafana-mcp-core)
#    ui    — React chat UI served via nginx
#
#  Usage:
#    docker compose build         # builds both targets
#    docker compose up -d         # starts core + ui
#    docker compose --profile demo up -d  # also starts Grafana
# ─────────────────────────────────────────────────────────────────

# ── Stage: Python deps (cached layer) ────────────────────────────
FROM python:3.11-slim AS python-deps

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install uv for fast dependency resolution
RUN pip install uv==0.5.29

# Copy workspace manifests first (layer-cache friendly)
COPY pyproject.toml ./
COPY packages/core/pyproject.toml ./packages/core/
COPY packages/sdk/pyproject.toml ./packages/sdk/

# Install production deps into /app/venv
RUN uv venv /app/venv && \
    uv pip install --python /app/venv/bin/python \
        "mcp[cli]>=1.6" \
        "httpx[http2]>=0.27" \
        "pydantic>=2.7" \
        "pydantic-settings>=2.3" \
        "structlog>=24.4" \
        "tenacity>=8.3" \
        "python-dotenv>=1.0" \
        "click>=8.1" \
        "starlette>=0.41" \
        "uvicorn[standard]>=0.30" \
        "anyio>=4.4"

# ── Stage: core ──────────────────────────────────────────────────
FROM python:3.11-slim AS core

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/venv/bin:$PATH" \
    VIRTUAL_ENV="/app/venv"

# Copy pre-built venv from deps stage
COPY --from=python-deps /app/venv /app/venv

WORKDIR /app

# Copy source packages
COPY packages/core/src ./packages/core/src
COPY packages/sdk/src  ./packages/sdk/src

# Install editable packages (source only, deps already in venv)
RUN pip install --no-deps -e ./packages/core -e ./packages/sdk

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash bifrost && \
    chown -R bifrost:bifrost /app
USER bifrost

# Health check endpoint exposed by the MCP SSE server
HEALTHCHECK --interval=15s --timeout=3s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request, sys; \
        r = urllib.request.urlopen('http://localhost:8765/healthz', timeout=2); \
        sys.exit(0 if r.status == 200 else 1)" || exit 1

EXPOSE 8765 8766

CMD ["grafana-mcp", "serve", "--transport", "sse", "--port", "8765"]

# ── Stage: ui-builder ────────────────────────────────────────────
FROM node:20-alpine AS ui-builder

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH"

RUN npm install -g pnpm@9

WORKDIR /app

# Copy workspace manifests first
COPY package.json pnpm-workspace.yaml* pnpm-lock.yaml* ./
COPY packages/ui/package.json ./packages/ui/

# Install node dependencies
RUN pnpm install --frozen-lockfile 2>/dev/null || pnpm install

# Copy source and build
COPY packages/ui/ ./packages/ui/
RUN pnpm --filter ./packages/ui build

# ── Stage: ui ────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS ui

# Copy compiled UI from builder
COPY --from=ui-builder /app/packages/ui/dist /usr/share/nginx/html

# nginx config for SPA routing (all paths → index.html)
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location /healthz {\n\
        return 200 "ok";\n\
        add_header Content-Type text/plain;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
