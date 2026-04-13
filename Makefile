# ─────────────────────────────────────────────────────────────────
#  Bifröst — Makefile
# ─────────────────────────────────────────────────────────────────

.PHONY: help install dev test lint fmt build docker clean demo \
        sdk-test ui-test core-test core-serve-sse core-serve-http \
        validate-config list-tools

help:               ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Install ────────────────────────────────────────────────────────
install:            ## Install everything (uv sync + pnpm install)
	uv sync --all-extras
	pnpm --filter ./packages/ui install

# ── Dev loop ───────────────────────────────────────────────────────
dev:                ## Boot demo Grafana + MCP server + UI (hot reload)
	docker compose --profile demo up -d grafana-demo
	@echo "→ waiting for Grafana to be healthy..."
	@until curl -sf http://localhost:3000/api/health > /dev/null; do sleep 1; done
	@echo "✓ Grafana ready on http://localhost:3000"
	$(MAKE) -j2 core-serve-sse ui-dev

ui-dev:             ## Run Vite dev server only
	pnpm --filter ./packages/ui dev

core-serve-sse:     ## Run MCP server in SSE mode (port 8765)
	uv run grafana-mcp serve --transport sse --env dev --role viewer --port 8765

core-serve-http:    ## Run MCP server in streamable HTTP mode (port 8766)
	uv run grafana-mcp serve --transport http --env dev --role admin --port 8766

# ── Test ───────────────────────────────────────────────────────────
test: core-test sdk-test ui-test  ## Run every test suite

core-test:          ## pytest on packages/core (90% coverage gate)
	uv run pytest packages/core/tests --cov=packages/core/src --cov-fail-under=90

sdk-test:           ## pytest on packages/sdk
	uv run pytest packages/sdk/tests

ui-test:            ## vitest on packages/ui
	pnpm --filter ./packages/ui test --run

# ── Lint / format ──────────────────────────────────────────────────
lint:               ## ruff + eslint + tsc --noEmit
	uv run ruff check packages/core packages/sdk
	uv run ruff format --check packages/core packages/sdk
	pnpm --filter ./packages/ui lint
	pnpm --filter ./packages/ui typecheck

fmt:                ## Apply ruff format + eslint --fix
	uv run ruff format packages/core packages/sdk
	uv run ruff check --fix packages/core packages/sdk
	pnpm --filter ./packages/ui lint --fix

# ── Build / docker ─────────────────────────────────────────────────
build:              ## Build the UI for production
	pnpm --filter ./packages/ui build

docker:             ## Build the multi-stage docker image
	docker compose build

# ── CLI conveniences ───────────────────────────────────────────────
validate-config:    ## Validate .env without booting the server
	uv run grafana-mcp validate-config

list-tools:         ## List every registered MCP tool with its min role
	uv run grafana-mcp list-tools

demo:               ## One-shot: build + boot demo + open the UI
	docker compose --profile demo up -d --build
	@echo "✓ open http://localhost:5173"

# ── Cleanup ────────────────────────────────────────────────────────
clean:              ## Stop everything + drop demo volume
	docker compose --profile demo down -v
	rm -rf packages/core/.coverage packages/core/htmlcov
	rm -rf packages/ui/dist packages/ui/node_modules/.vite
