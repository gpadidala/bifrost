# Contributing to Bifröst

Thanks for considering a contribution! Bifröst is a small project and PRs are reviewed quickly. This page describes the local dev loop, code style, and the conventions we hold each other to.

## Required reading first

Before opening Claude Code on this repo, read [docs/guides/agent-skills.md](docs/guides/agent-skills.md). Bifröst is built with two enforced skill packs — `agent-skills` (workflow gates) and `ui-ux-pro-max` (design intelligence). The doc explains the slash commands, the skill → deliverable mapping, the per-package workflow, the pre-delivery checklist, and the anti-rationalization table. **Do not skip it.**

The [CLAUDE.md](CLAUDE.md) at the repo root is what Claude Code reads at session start — it points at the same workflow.

## Local development

```bash
git clone https://github.com/gpadidala/bifrost.git
cd bifrost

# Install the workspace (core + sdk + ui dev deps)
uv sync
pnpm --filter ./packages/ui install

# Boot the demo Grafana + MCP server
make dev
```

`make dev` runs `docker compose --profile demo up` to give you a pre-seeded Grafana on `:3000`, then starts the MCP server on `:8765` (SSE) and the Vite dev server on `:5173`. The first run takes ~90 seconds while compose pulls images.

## Repository layout

```
bifrost/
├── packages/
│   ├── core/          # Python MCP server (FastAPI + mcp[cli])
│   ├── ui/            # React + Vite + Tailwind v4
│   └── sdk/           # Python developer SDK
├── .vscode/           # MCP extension config + tasks + launch configs
├── docs/              # All documentation (Markdown only)
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml     # uv workspace root
└── Makefile
```

## Code style

### Python (`packages/core`, `packages/sdk`)

- **Type everything.** `from __future__ import annotations` at the top of every file.
- **Pydantic v2** for every data boundary — MCP tool inputs, MCP tool outputs, settings, Grafana API responses.
- **No `Any`** without a `# type: ignore[...]` comment explaining why.
- **`ruff`** is the only linter and formatter. Run `make lint`.
- **`pytest-asyncio`** for async tests, **`respx`** to mock `httpx`.
- Test coverage gate: **90%** on `packages/core`. CI fails below.

### TypeScript (`packages/ui`)

- `"strict": true`, `"noUncheckedIndexedAccess": true`. **No `any`** — use `unknown` and narrow.
- Functional components only. Hooks for state, no class components.
- Zustand for global state, TanStack Query for server state, `useState` for local.
- Every async path handles loading + error + success — no silent failures.
- ARIA labels and keyboard navigation are non-negotiable for any new component.

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(core): add silence_alert tool
fix(ui): correct env switcher when role is admin
docs: clarify SSE vs HTTP transport tradeoffs
chore(deps): bump httpx to 0.28
```

Allowed types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `ci`. Scope is the package or area (`core`, `ui`, `sdk`, `docs`, `vscode`).

## Adding a new MCP tool

1. Define Pydantic input + output models in `packages/core/src/grafana_mcp/schemas/`.
2. Add the async function in the appropriate `tools/<group>.py` module, decorated with `@mcp.tool()`.
3. If it's not a `viewer`-level tool, add an entry to `TOOL_MINIMUM_ROLE` in `packages/core/src/grafana_mcp/rbac.py`.
4. Write a `respx`-mocked unit test under `packages/core/tests/tools/`.
5. Document the tool in [docs/api/mcp-tools-reference.md](docs/api/mcp-tools-reference.md).

The role table is the **single source of truth** for RBAC. If you forget to update it, the tool defaults to `viewer` — which is a security footgun for any write/admin tool. CI runs a check that warns if a new tool is missing from the table.

## Pull request checklist

- [ ] `make lint` passes
- [ ] `make test` passes (90%+ coverage on `core`)
- [ ] Added/updated docs in `docs/` if behavior changed
- [ ] Added/updated `CHANGELOG.md` under `## Unreleased`
- [ ] Conventional commit messages
- [ ] No service-account tokens or `.env` values in the diff (check twice — `glsa_...` strings are auto-rejected by CI)

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) and include:

- Bifröst version (`grafana-mcp --version`)
- Grafana version (OSS or Enterprise)
- Transport (`sse` / `http`) and active role
- Minimal reproduction (env vars *with tokens redacted*, command, expected vs actual)
- Relevant `grafana-mcp` log lines — auth headers are auto-redacted, paste freely

## Code of conduct

Be kind. Assume good faith. Disagree with ideas, not people. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
