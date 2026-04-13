# Bifröst — Claude Code Configuration

## Project

**Bifröst** is the rainbow bridge between LLMs and Grafana — a multi-transport, multi-role, multi-environment MCP server framework.

Three packages:

- **`packages/core`** — Python MCP server (FastAPI + `mcp[cli]`, SSE + streamable HTTP transports)
- **`packages/ui`** — React 19 + Vite 6 + TypeScript 5.5 chat & config UI
- **`packages/sdk`** — Python developer SDK with sync + async APIs

See [README.md](README.md) and [docs/architecture/overview.md](docs/architecture/overview.md) for the full architecture spec.

## Skills

Two skill packs are installed for this repo. Use the right one for the right phase.

### `agent-skills` (`.agent-skills/skills/`) — workflow enforcement

Workflow enforcement for every SDLC phase. Provides slash commands `/spec`, `/plan`, `/build`, `/test`, `/review`, `/ship`. **Never skip a skill because "the task seems simple."** The complexity is in the integration — three roles × three environments × two transports × N tools is a combinatorial space, not a checklist.

### `ui-ux-pro-max` (`.claude/skills/ui-ux-pro-max/`) — design intelligence

Auto-activates on any UI/UX request inside `packages/ui/`. Contains 50+ styles, 161 color palettes, 57 font pairings, and 99 UX guidelines. Search the design database **before** making any visual decision:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "dark developer tool" --domain styles -n 5
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "monospace JetBrains" --domain google-fonts -n 3
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "developer dashboard dark" --domain colors -n 5
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "time series line chart dark" --domain charts -n 3
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "admin panel dark UX" --domain ux-guidelines -n 5
```

The full skill setup, slash-command mapping, and pre-delivery checklist live in [docs/guides/agent-skills.md](docs/guides/agent-skills.md). **Read it before writing any code.**

## Slash commands available

| Command | Use it for |
|---|---|
| `/spec` | Write structured spec **before** touching code. Contracts, schemas, edge cases. |
| `/plan` | Break work into verifiable tasks with explicit acceptance criteria. |
| `/build` | Implement one thin slice at a time. |
| `/test` | TDD — failing test first, then implementation. |
| `/review` | Multi-axis code review before considering a phase complete. |
| `/ship` | Pre-launch checklist before tagging any release. |

## Tech stack

- **Python:** FastAPI, `mcp[cli]>=1.6`, Pydantic v2, `httpx[http2]`, structlog, ruff, pytest-asyncio, respx, tenacity
- **React:** TypeScript 5.5 strict, Vite 6, Zustand, TanStack Query v5, Radix UI, Tailwind v4, `@anthropic-ai/sdk`, `openai`
- **Tooling:** uv workspaces, pnpm, docker-compose, Makefile

## UI design system (`packages/ui`)

**Stack:** React (pass `--stack react` to `search.py`)

**Theme:** Dark developer power tool — **NOT** a consumer app. **NOT** purple gradients on white. The reference is Linear / GitHub Dark / Vercel dashboard, not Stripe marketing.

**Locked design choices** (confirmed via `ui-ux-pro-max` database — do not override without re-running the generator):

| | |
|---|---|
| **Style** | Dark mode + glassmorphism for panel surfaces |
| **Typography** | JetBrains Mono (code/tokens/URLs) + IBM Plex Sans (UI copy) |
| **Palette** | Deep dark `#0d0d12` base, electric amber `#f59e0b` accent, status green `#22c55e` / red `#ef4444` |
| **Charts** | `ui-ux-pro-max` chart database — search "time series dashboard" for Grafana panel previews |
| **Spacing** | 8pt grid system (`4`, `8`, `16`, `24`, `32`, `48`, `64`) |

Run the design system generator **before writing any component**:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/design_system.py \
  "Bifröst — Grafana MCP developer tool, dark UI, three-env config, AI chat, role switcher" \
  --stack react > packages/ui/DESIGN_SYSTEM.md
```

`packages/ui/DESIGN_SYSTEM.md` is committed to the repo and is the single source of truth for visual decisions. Component code references it via CSS custom properties in `tokens.css` — never hardcode hex values.

## Quality gates (non-negotiable)

- No package ships without passing tests (90% line coverage on `packages/core`)
- No tool added to MCP server without a Pydantic input model **and** a Pydantic output model
- No tool added without an entry in `TOOL_MINIMUM_ROLE` (or an explicit `viewer` comment)
- No React component without TypeScript strict types — no `any` without an inline justification comment
- No Grafana API call without role enforcement checked
- No UI component ships without passing the `ui-ux-pro-max` pre-delivery checklist
- No commit with `glsa_...` strings or other secrets in the diff (CI rejects)

## Structure

```
bifrost/
├── packages/
│   ├── core/          # Python MCP server
│   ├── ui/            # React config + AI chat app
│   └── sdk/           # Python developer SDK
├── .vscode/           # VSCode MCP config + tasks + launch + settings
├── docs/              # All documentation
├── .agent-skills/     # agent-skills plugin (read-only — do not edit)
└── .claude/skills/ui-ux-pro-max/   # UI design intelligence (read-only — do not edit)
```

## Boundaries

- **Never mix role tokens across requests** — one role per call, period
- **Never hardcode service-account tokens** — always from `Settings` / env / `.grafana-mcp.toml`
- **Never use `any` in TypeScript** without an inline justification comment
- **Never skip the verification step** at the end of each skill workflow
- **Never choose colors, fonts, or spacing** without querying the `ui-ux-pro-max` database first
- **Never add a fourth role** — `viewer / editor / admin` is the schema. See [docs/architecture/role-model.md](docs/architecture/role-model.md#adding-a-new-role)
- **Never add a fourth environment name** — `dev / perf / prod` is the schema. See [docs/architecture/environments.md](docs/architecture/environments.md#why-three-named-environments)

## Definition of Done

The build is complete when **all** of the following are true — not before:

- [ ] `make test` → 100% pass, ≥90% coverage on core + sdk
- [ ] `make lint` → zero ruff warnings, zero TypeScript errors
- [ ] `make build` → Docker images build, UI bundle produced
- [ ] `/review` run on each package by `code-reviewer` agent — all issues resolved
- [ ] `/review` run on token handling by `security-auditor` agent — zero findings
- [ ] VSCode: `MCP: Connect to Server` works with both `sse` and `http` transport
- [ ] UI: all three environments configurable, health check green, chat sends real tool calls
- [ ] SDK: `grafana-sdk shell --env dev` opens a REPL that can call `list_dashboards()`
- [ ] `CHANGELOG.md` updated, `README.md` Quick Start works from a clean clone
- [ ] All ADRs written (transport choice, role enforcement approach, token storage in UI)
- [ ] **UI:** `DESIGN_SYSTEM.md` exists — generated by `ui-ux-pro-max`, committed to repo
- [ ] **UI:** all components pass the `ui-ux-pro-max` pre-delivery checklist (no contrast failures, no hardcoded hex, no missing ARIA labels)
- [ ] **UI:** design system search queries for each component logged in `packages/ui/design-decisions.md`
- [ ] **UI:** Lighthouse accessibility score ≥ 90 on the connection config page and the chat interface
