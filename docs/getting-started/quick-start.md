# Quick Start

This page assumes you've finished [Installation](installation.md) and have at least one environment configured in `.env`. We'll walk through three things:

1. Boot the MCP server
2. Connect from the React UI and run a tool from the chat
3. Connect from VSCode and run a tool from Copilot Chat

The whole loop takes about 3 minutes.

## 1. Boot the server

Pick the environment + role you want for this session. For first-time setup, `dev` + `viewer` is the safe default — no write access, no surprises.

```bash
uv run grafana-mcp serve \
  --transport sse \
  --env dev \
  --role viewer \
  --port 8765
```

You should see:

```
{"level":"info","event":"settings.loaded","environment":"dev","role":"viewer"}
{"level":"info","event":"grafana.health_check","status":"ok","latency_ms":42}
{"level":"info","event":"server.starting","transport":"sse","port":8765,"path":"/mcp/sse"}
✓ Bifröst MCP server listening on http://0.0.0.0:8765/mcp/sse
```

If the `grafana.health_check` line shows `status:"error"`, your token or base URL is wrong. Re-check `.env` and run `grafana-mcp validate-config`.

## 2. Connect the React UI

In a new terminal:

```bash
pnpm --filter ./packages/ui dev
# → http://localhost:5173
```

Open the URL. You should see the **Connection Config** screen with three environment cards (`dev`, `perf`, `prod`).

1. The `dev` card should already show **Connected** in green — it picked up the running server automatically.
2. Drop in your **Anthropic** or **OpenAI** API key in the **LLM** drawer (top-right gear icon). Pick a model — `claude-sonnet-4-20250514` is a sensible default.
3. Click **Chat** in the sidebar.
4. Type:

   > List all the dashboards in this Grafana instance.

The LLM will call `list_dashboards` via the live MCP server. You'll see the tool call expand inline as a collapsible card showing the params (`{}`) and the result (a JSON list of dashboards). The LLM then summarizes the result in natural language.

That's the full loop: **prompt → LLM → MCP tool → Grafana → result → LLM → answer**.

## 3. Connect from VSCode

The repo ships with a working `.vscode/mcp.json`. Open the workspace in VSCode and:

1. Install the **MCP** extension (and Copilot Chat or Claude Code, whichever you use).
2. Open the command palette → **MCP: Connect to Server** → pick `grafana-dev-viewer`.
3. Open Copilot Chat (or Claude Code) and ask:

   > What datasources are configured in this Grafana?

The agent will list the available MCP tools, pick `list_datasources`, call it through Bifröst, and answer. No extra wiring.

For the editor or admin servers, use the matching VSCode tasks (**Cmd-Shift-P → Run Task → MCP: Start Dev Server (SSE, Editor)**) and switch the server in **MCP: Connect to Server**.

## What's next?

- **Try a write operation.** Restart the server with `--role editor` and ask the LLM "silence the foo alert for 30 minutes" — you'll see the role enforcement allow `silence_alert` that was previously blocked.
- **Explore the resource tree.** The UI's left panel is a live tree of folders → dashboards → panels, fed by MCP calls. Click any node to drop a context card into the chat.
- **Use the SDK from a notebook.** See the [SDK reference](../api/sdk-reference.md) for `GrafanaMCP.from_env()`.
- **Read the [Configuration Reference](configuration.md)** to understand every env var.
- **Read [First Run Walkthrough](first-run.md)** for screenshots and a guided tour.
