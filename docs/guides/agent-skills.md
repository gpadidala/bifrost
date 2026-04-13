# agent-skills + ui-ux-pro-max Integration

Bifröst is built with **enforced workflows**, not shortcuts. Two skill packs run alongside Claude Code and gate every phase of the build:

- **[agent-skills](https://github.com/addyosmani/agent-skills)** by Addy Osmani — workflow enforcement for spec → plan → build → test → review → ship
- **[ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)** — design intelligence with 50+ UI styles, 161 color palettes, 57 font pairings, 99 UX guidelines, plus a chart database

This page is the operating manual for both. Read it once before opening Claude Code on this repo.

> The contents of this page are the *enforced* part of the build process. The README explains *what* Bifröst is; this page explains *how* the team ships it without cutting corners.

---

## 🔧 Setup — install both skill packs

Run these once in the Bifröst repo root.

### 1. agent-skills

```bash
git clone https://github.com/addyosmani/agent-skills.git .agent-skills
claude --plugin-dir .agent-skills

# Or via the npx helper:
npx add-skill addyosmani/agent-skills
```

### 2. ui-ux-pro-max-skill

Pick whichever path matches your setup:

```bash
# Option A — Claude Code marketplace (recommended)
/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill
/plugin install ui-ux-pro-max@nextlevelbuilder-ui-ux-pro-max-skill

# Option B — npm CLI
npm install -g uipro-cli
uipro init --ai claude

# Option C — manual clone
git clone https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git .ui-ux-skill
cp -r .ui-ux-skill/.claude/skills/ui-ux-pro-max .claude/skills/
```

After install, `.claude/skills/` contains both `agent-skills` and `ui-ux-pro-max`. The slash commands `/spec`, `/plan`, `/build`, `/test`, `/review`, `/ship` become available in Claude Code automatically.

Verify:

```bash
ls .agent-skills/skills/        # workflow skills
ls .claude/skills/ui-ux-pro-max # design intelligence
ls .claude/commands/            # /spec, /plan, /build, /test, /review, /ship
```

If `.claude/commands/` is empty, the skill packs didn't wire correctly — re-run the install.

---

## 🗺️ Skill → Deliverable mapping

Every step in the [Bifröst deliverable order](../../README.md#-roadmap) maps to an exact `agent-skills` skill that Claude Code must load **before** implementing. This is non-negotiable — it's why Bifröst doesn't ship with stub MCP tools or untyped React components.

| Step | Deliverable | Skill to invoke | Slash command |
|------|---|---|---|
| 1 | Pydantic config models + Settings | `spec-driven-development` | `/spec` |
| 2 | `GrafanaClient` (httpx, retry, pool) | `api-and-interface-design` | `/build` |
| 3 | MCP server — all tools | `incremental-implementation` + `test-driven-development` | `/build` + `/test` |
| 3a | Role enforcement middleware | `security-and-hardening` | `/review` |
| 4 | CLI entry points + tests | `test-driven-development` | `/test` |
| 5 | VSCode config files | `context-engineering` | `/build` |
| 6 | Python SDK | `api-and-interface-design` + `incremental-implementation` | `/build` |
| 7 | **React connection config UI** | `frontend-ui-engineering` + **`ui-ux-pro-max`** | `/build` |
| 8 | **LLM config panel** | `incremental-implementation` + **`ui-ux-pro-max`** | `/build` |
| 9 | **AI chat + MCP tool calling** | `incremental-implementation` + `browser-testing-with-devtools` + **`ui-ux-pro-max`** | `/build` + `/test` |
| 10 | **Grafana resource explorer** | `frontend-ui-engineering` + **`ui-ux-pro-max`** | `/build` |
| 11 | Docker + Makefile + README | `documentation-and-adrs` + `shipping-and-launch` | `/ship` |

**Before each step:** invoke the mapped skill via the slash command. **After each step:** run `/review` — do not proceed until the review passes.

---

## 🔁 Enforced workflow per package

### `packages/core` — Python MCP Server

```
/spec   → Write SPEC.md: all 20+ MCP tools, role table, transport modes, env model
/plan   → tasks/core-plan.md: one task per tool group, explicit acceptance criteria
/build  → implement GrafanaClient first (no MCP yet), all methods tested with respx
/test   → pytest coverage report must show ≥90% on grafana_client.py before moving on
/build  → implement MCP tools one group at a time (dashboards, datasources, alerts, admin)
/test   → integration test each tool group with a mock Grafana server
/review → security-and-hardening skill: token injection, no secrets in logs, retry logic
/ship   → CLI works: `grafana-mcp serve --transport sse --env dev --role viewer`
```

### `packages/sdk` — Python Developer SDK

```
/spec   → SDK contract: sync/async wrappers, config source priority, .toml format
/plan   → tasks/sdk-plan.md
/build  → implement async client first, sync wrapper second, CLI third
/test   → test all three config sources (explicit, .toml, env vars) in priority order
/review → code-simplification skill: SDK surface must be minimal and intuitive
/ship   → `pip install packages/sdk` works in a clean venv
```

### `packages/ui` — React App + ui-ux-pro-max design intelligence

#### Phase 0 — Design System (run **before** any code)

Search the `ui-ux-pro-max` database to confirm design decisions:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "dark developer dashboard" --stack react --domain styles -n 5
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "developer tool dark amber" --domain colors -n 5
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "JetBrains monospace pairing" --domain google-fonts -n 3
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "time series line chart dark" --domain charts -n 3
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "admin panel dark UX" --domain ux-guidelines -n 5
```

Generate the full design system (run once, save output):

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/design_system.py \
  "Bifröst — Grafana MCP developer tool, dark UI, three-env config, AI chat, role switcher" \
  --stack react > packages/ui/DESIGN_SYSTEM.md
```

`packages/ui/DESIGN_SYSTEM.md` becomes the **single source of truth** for visual decisions. Commit it to the repo. Components reference its tokens via `tokens.css` — never hardcode hex values.

#### Phase 1 — Build order

Each step: implement → `ui-ux-pro-max` pre-delivery check → commit.

```
/spec   → UI spec: connection panel wireframe, LLM panel fields, chat interface flows
          Reference DESIGN_SYSTEM.md for all visual decisions in the spec
/plan   → tasks/ui-plan.md: component tree, store shape, API surface

/build  → Zustand stores (connectionStore, chatStore) — no UI yet
/test   → unit test store actions and selectors

/build  → Design tokens: CSS custom properties from DESIGN_SYSTEM.md → tokens.css
          Verify: all colors from palette, all fonts from typography section, 8pt grid vars

/build  → Connection config panel
          Before writing: search "form input dark" and "env switcher segmented control" --domain ux-guidelines
          After writing: run ui-ux-pro-max pre-delivery checklist (see below)

/build  → Health check integration (TanStack Query) + status badges
          Before writing: search "status indicator badge dark" --domain ux-guidelines

/build  → LLM config panel (provider picker, model dropdown, API key field)
          Before writing: search "settings panel dark drawer" --domain ux-guidelines

/build  → Chat interface (streaming tokens, tool call cards, markdown render)
          Before writing: search "chat interface dark streaming" --domain styles
          After writing: run ui-ux-pro-max pre-delivery checklist

/build  → Grafana resource explorer (tree view, lazy load, context cards)
          Before writing: search "tree view sidebar dark developer" --domain ux-guidelines

/test   → browser-testing-with-devtools: run against live MCP server, capture network traces
/review → performance-optimization: bundle size, no unnecessary re-renders
/ship   → `vite build` produces <500 KB gzipped bundle
```

---

## ✅ ui-ux-pro-max Pre-Delivery Checklist

Run this checklist after **every** UI component. Do not commit a component until all items pass.

### Accessibility

- [ ] Color contrast ≥ 4.5:1 for all text (check amber on dark background)
- [ ] All interactive elements have ARIA labels (`role="button"`, `aria-label`, etc.)
- [ ] Keyboard navigation works: Tab order logical, Enter/Space triggers actions
- [ ] Focus rings visible in keyboard navigation mode
- [ ] All form inputs have associated `<label>` elements

### Visual consistency

- [ ] Colors sourced **only** from `tokens.css` (no hardcoded hex values)
- [ ] Typography: JetBrains Mono for all code/tokens/URLs, IBM Plex Sans for UI copy
- [ ] Spacing follows 8pt grid (`4`, `8`, `16`, `24`, `32`, `48`, `64` only)
- [ ] Dark mode: both themes tested (dark is primary; light must not break if toggled)
- [ ] Surfaces use the design system glass/card treatment — no raw white backgrounds

### Interaction states

- [ ] All buttons: `default`, `hover`, `active`, `disabled`, `loading` states implemented
- [ ] All inputs: `default`, `focus`, `error`, `success` states implemented
- [ ] Status badges (connected/error/untested): correct color per state
- [ ] Streaming indicator (SSE pulse) visible and semantically meaningful

### Performance (React-specific)

- [ ] No unnecessary re-renders: `memo` / `useCallback` used where the profiler shows waste
- [ ] Images: WebP format, explicit `width`/`height` to prevent CLS
- [ ] Lazy loading on Grafana resource explorer tree nodes
- [ ] TanStack Query: `staleTime` and `gcTime` set — no waterfall fetches

### Developer-tool specific

- [ ] Service-account token inputs: `type="password"`, never logged to console
- [ ] Error states include actionable message (not just "Error")
- [ ] Tool-call cards in chat: collapsible, show tool name + params + result clearly
- [ ] Environment selector: active env visually distinct, never ambiguous

---

## 🪝 Hooks configuration

Create these in `.agent-skills/hooks/` — they fire automatically in every Claude Code session.

### `session-start.md`

```markdown
## On Every Session Start

1. Run `git status` — confirm you're on a feature branch, not main
2. Run `uv run pytest packages/core/tests/ -x -q` — confirm tests pass before touching code
3. Run `cd packages/ui && npx tsc --noEmit` — confirm TypeScript clean
4. Check tasks/todo.md for current task — pick the next unchecked item
5. Load the skill mapped to that task (see SKILL → DELIVERABLE MAPPING in CLAUDE.md)
```

### `pre-commit.md`

```markdown
## Before Every Commit

1. `uv run ruff check packages/core packages/sdk` — zero warnings
2. `uv run ruff format packages/core packages/sdk` — auto-format
3. `cd packages/ui && npx tsc --noEmit` — TypeScript clean
4. `uv run pytest packages/core packages/sdk -x -q` — all tests pass
5. Commit message must follow Conventional Commits: feat / fix / chore / test / docs
6. Never commit .env files, service-account tokens, or hardcoded credentials
```

---

## 🤖 Agent personas — when to invoke

Three specialist agents from `.agent-skills/agents/`. Use them at these trigger points:

| Agent | File | When to invoke |
|---|---|---|
| `code-reviewer` | `agents/code-reviewer.md` | After completing each full package (`core`, `sdk`, `ui`) |
| `security-auditor` | `agents/security-auditor.md` | After implementing role enforcement, token handling, and the UI's localStorage encryption |
| `test-engineer` | `agents/test-engineer.md` | When test coverage drops below 90% on `core`, or when chat streaming tests flake |

Usage in Claude Code:

```
"Review packages/core using the code-reviewer agent persona.
Load the agent definition from .agent-skills/agents/code-reviewer.md."
```

---

## 🚩 Anti-rationalization table

These are the excuses Claude Code (or you) will be tempted to use to skip skills. **All are invalid.** Counter-arguments are final.

| Excuse | Counter |
|---|---|
| "The config models are simple, no spec needed" | The role/env/transport model has 3-way interactions. Spec it or you'll miss edge cases. |
| "I'll add tests after the MCP tools are wired up" | Tools not covered by tests are broken by default. `/test` runs **before** `/build` completes. |
| "The UI is config forms, no security review needed" | Service-account tokens in localStorage need crypto review. Load `security-and-hardening`. |
| "The SDK API is obvious, no interface design skill needed" | The SDK is a public developer surface. Breaking changes cost real developer time. Spec the contract. |
| "The review step is slow, the code looks fine" | "Looks fine" is not evidence. `/review` produces a checklist. Every item must pass. |
| "I'll document after all three packages ship" | ADRs written after the fact are post-hoc rationalization. Document the `TransportConfig` decision now. |
| "I already know the design — dark theme, amber accent, done" | Run the `ui-ux-pro-max` search anyway. 161 palettes exist. Your instinct might miss the right contrast ratio. |
| "The font is already in the master prompt, no need to search" | The master prompt sets direction. The `ui-ux-pro-max` database validates it and provides the exact Google Fonts import URL + CSS vars. |
| "The pre-delivery checklist is for consumer apps, not dev tools" | Developer tools have **worse** accessibility debt than consumer apps. The checklist is non-negotiable regardless of audience. |
| "I'll fix the contrast ratio later" | Contrast failures block the `security-auditor` review. Fix it before committing the component. |

---

## ✅ Definition of Done

The build is complete when **all** of the following are true — not before:

- [ ] `make test` → 100% pass, ≥90% coverage on `core` + `sdk`
- [ ] `make lint` → zero ruff warnings, zero TypeScript errors
- [ ] `make build` → Docker images build, UI bundle produced
- [ ] `/review` run on each package by `code-reviewer` agent — all issues resolved
- [ ] `/review` run on token handling by `security-auditor` agent — zero findings
- [ ] VSCode: `MCP: Connect to Server` works with both `sse` and `http` transport
- [ ] UI: all three environments configurable, health check green, chat sends real tool calls
- [ ] SDK: `grafana-sdk shell --env dev` opens a REPL that can call `list_dashboards()`
- [ ] `CHANGELOG.md` updated, `README.md` Quick Start works from a clean clone
- [ ] All ADRs written: transport choice, role enforcement approach, token storage in UI
- [ ] **UI:** `DESIGN_SYSTEM.md` exists — generated by `ui-ux-pro-max`, committed to repo
- [ ] **UI:** all components pass the `ui-ux-pro-max` pre-delivery checklist (no contrast failures, no hardcoded hex, no missing ARIA labels)
- [ ] **UI:** design system search queries for each component logged in `packages/ui/design-decisions.md` (what was searched, what was chosen, why)
- [ ] **UI:** Lighthouse accessibility score ≥ 90 on the connection config page and the chat interface

---

## Related

- [CLAUDE.md](../../CLAUDE.md) — top-level Claude Code config that wires this in
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — code style and PR conventions
- [Architecture overview](../architecture/overview.md)
- [`packages/ui` reference](../packages/ui.md)
