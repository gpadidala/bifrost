# VSCode Integration

Bifröst is designed to be a first-class VSCode citizen. The repo ships with `.vscode/mcp.json`, `tasks.json`, `launch.json`, `extensions.json`, and `settings.json` so that opening the workspace gives you a working dev loop in under a minute.

## What you get

- **MCP servers** declared in `.vscode/mcp.json` — drop into Copilot Chat / Claude Code / Cursor / Cline immediately
- **Background tasks** to start each server flavor (dev/viewer, dev/editor, prod/admin, streamable HTTP)
- **Launch configs** for debugging the MCP server, the SDK CLI, the Vite dev server, and pytest
- **Settings** for ruff format-on-save, strict pyright, Tailwind class detection, and pytest discovery
- **Extension recommendations** so first-time openers get prompted to install the right toolchain

## `.vscode/mcp.json`

The MCP extension reads this file to discover available MCP servers. Bifröst ships with four pre-configured servers covering the most common (env, role) combinations:

```json
{
  "servers": {
    "grafana-dev-viewer":  { "type": "sse", "url": "http://localhost:8765/mcp/sse", "label": "Grafana — Dev (Viewer)" },
    "grafana-dev-editor":  { "type": "sse", "url": "http://localhost:8767/mcp/sse", "label": "Grafana — Dev (Editor)" },
    "grafana-perf-viewer": { "type": "sse", "url": "http://localhost:8768/mcp/sse", "label": "Grafana — Perf (Viewer)" },
    "grafana-prod-admin":  { "type": "sse", "url": "http://localhost:8766/mcp/sse", "label": "Grafana — Prod (Admin)" }
  }
}
```

The labels intentionally include the env and role so you can tell from a glance which connection you're using in Copilot Chat. Add or remove entries to match your real environments.

> 📝 **Why all SSE?** The VSCode MCP extension currently supports SSE only. If you need streamable HTTP, use the Python SDK from a notebook or terminal — the SDK is the right tool for that wire format.

## `.vscode/tasks.json`

Each task starts a different flavor of the MCP server in the background, plus convenience tasks for tests, linting, and the demo:

| Task label | Command |
|---|---|
| **MCP: Start Dev Server (SSE, Viewer)** | `uv run grafana-mcp serve --transport sse --env dev --role viewer --port 8765` |
| **MCP: Start Dev Server (SSE, Editor)** | `uv run grafana-mcp serve --transport sse --env dev --role editor --port 8767` |
| **MCP: Start Prod Server (SSE, Admin)** | `uv run grafana-mcp serve --transport sse --env prod --role admin --port 8766` |
| **MCP: Start Streamable HTTP Server (Dev, Admin)** | `uv run grafana-mcp serve --transport http --env dev --role admin --port 8769` |
| **UI: Vite Dev Server** | `pnpm --filter ./packages/ui dev` |
| **Test: All Packages** | `make test` |
| **Lint: All Packages** | `make lint` |
| **Demo: Boot Everything** | `make demo` |
| **Validate: .env config** | `uv run grafana-mcp validate-config` |

The server tasks are marked `"isBackground": true` with a problemMatcher that watches for the `listening on http` log line. VSCode considers the task "started" once that line appears, so dependent tasks (or compound debugger configs) can chain off it.

To run a task: **Cmd-Shift-P → Run Task → pick one**.

## `.vscode/launch.json`

Debug configurations cover the four most common debugging scenarios:

| Config | What it debugs |
|---|---|
| **Debug: MCP Server (SSE, Dev, Viewer)** | The Python MCP server with breakpoints |
| **Debug: MCP Server (HTTP, Dev, Admin)** | Same, streamable HTTP transport |
| **Debug: SDK CLI** | The `grafana-sdk run` command — useful when adding new tool surface |
| **Debug: Core Tests** | `pytest packages/core/tests` with breakpoints |
| **Debug: UI Vite Dev Server** | The Vite dev server (Node debugging) |
| **Debug: UI in Chrome** | Chrome devtools attached to the Vite-served app |

There's also a **compound** config:

- **Debug: Full Stack (MCP SSE + UI)** — boots both the MCP server and the Vite dev server with breakpoints attached to both, in one click

This is the right starting point for "I'm changing a tool and want to see it land in the chat UI."

## `.vscode/settings.json`

Workspace settings that match the [Code Style](../../CONTRIBUTING.md#code-style) section of CONTRIBUTING:

- `python.defaultInterpreterPath: ".venv/bin/python"` — picks up the uv-created venv
- `python.analysis.typeCheckingMode: "strict"` — strict pyright
- `python.testing.pytestEnabled: true` + paths to both test directories
- Format-on-save with **ruff** for Python, **prettier** for TypeScript
- Tailwind v4 class detection with the `cva()` and `cn()` regexes
- File excludes for `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.venv`

## `.vscode/extensions.json`

Opening the workspace prompts you to install the recommended extensions:

- **github.copilot** + **github.copilot-chat** — Copilot Chat is the easiest MCP host
- **anthropic.claude-code** — Claude Code, alternative MCP host
- **ms-python.python** + **ms-python.vscode-pylance** + **ms-python.debugpy**
- **charliermarsh.ruff** — Python lint + format
- **tamasfe.even-better-toml** — for `pyproject.toml` editing
- **esbenp.prettier-vscode** + **dbaeumer.vscode-eslint** — TS lint + format
- **bradlc.vscode-tailwindcss** — Tailwind class autocomplete
- **ms-azuretools.vscode-docker** — for the compose file
- **redhat.vscode-yaml** — for tasks.json + compose.yml validation
- **yzhang.markdown-all-in-one** — for editing the docs/

## A typical session

1. Open the workspace in VSCode
2. Click **Install All** when prompted for recommended extensions
3. Open the command palette → **Run Task** → **Demo: Boot Everything (Grafana + MCP + UI)**
4. Wait ~30 seconds for Grafana + MCP + UI to come up
5. Open the command palette → **MCP: Connect to Server** → pick **Grafana — Dev (Viewer)**
6. Open Copilot Chat (or Claude Code)
7. Ask: *"What dashboards exist in this Grafana?"*
8. Watch the LLM call `list_dashboards` through the MCP extension and answer

That's the whole loop. From `git clone` to first answer is under 5 minutes if you have Docker running.

## Switching servers mid-session

In Copilot Chat / Claude Code, the MCP server picker is in the chat input area. Click it, pick a different server, and the chat is now talking to that server. Useful for:

- "Read from prod, write to dev" — switch from `grafana-prod-admin` to `grafana-dev-editor` between turns
- "Compare dev to perf" — switch back and forth in one conversation

## Editing the MCP server list

If you want to add a new server (e.g., a `grafana-staging-editor` running on a different port), edit `.vscode/mcp.json` and reload the MCP extension. No restart needed.

## Troubleshooting

| Symptom | Fix |
|---|---|
| **MCP servers don't appear in Copilot Chat** | Reload the MCP extension: Cmd-Shift-P → "Developer: Reload Window" |
| **"Connection refused" on the SSE URL** | The MCP server task isn't running — start one of the **MCP: Start ...** tasks first |
| **Task starts but the chat says "no tools"** | The task started but Grafana ping failed. Check the task terminal for `health_check` errors |
| **`uv: command not found`** | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh`, then reload window |
| **`pnpm: command not found`** | Enable corepack: `corepack enable`, then `pnpm install` |
| **Breakpoints don't hit in MCP server debug** | The MCP request is being handled by a different process. Make sure you're debugging the right port and the task isn't already running on it |

## Related

- [Quick Start](../getting-started/quick-start.md)
- [Docker deployment](docker.md)
- [Troubleshooting guide](../guides/troubleshooting.md)
