// Developer setup guides embedded in the UI.
// Live values (URL, env, role) are pulled from the current Bifröst server-info
// so the snippets are always copy-pastable against the user's running instance.

import { useState, type ReactNode } from "react";
import type { ServerInfo } from "./api";

interface GuideProps {
  info: ServerInfo | null;
  serverUrl: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared CodeBlock with copy button
// ─────────────────────────────────────────────────────────────────────────────

export function CodeBlock({ lang, children }: { lang?: string; children: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* silent */
    }
  };
  return (
    <div className="code-block">
      <div className="code-block-header">
        {lang && <span className="code-lang">{lang}</span>}
        <button className="code-copy" onClick={copy} aria-label="Copy to clipboard">
          {copied ? "✓ copied" : "copy"}
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="step">
      <div className="step-num">{n}</div>
      <div className="step-body">
        <h4>{title}</h4>
        {children}
      </div>
    </div>
  );
}

function Note({ kind = "info", children }: { kind?: "info" | "warn" | "ok"; children: ReactNode }) {
  return <div className={`note ${kind}`}>{children}</div>;
}

// ─────────────────────────────────────────────────────────────────────────────
// VSCode guide
// ─────────────────────────────────────────────────────────────────────────────

export function VSCodeGuide({ info, serverUrl }: GuideProps) {
  const env = info?.active_environment ?? "dev";
  const role = info?.active_role ?? "viewer";
  const port = info?.transport.port ?? 8765;
  const prefix = info?.transport.path_prefix ?? "/mcp";
  const sseUrl = `${serverUrl}${prefix}/sse`;

  const mcpJson = `{
  "servers": {
    "bifrost-${env}-${role}": {
      "type": "sse",
      "url": "${sseUrl}",
      "label": "Grafana — ${env} (${role})"
    }
  }
}`;

  const tasksJson = `{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Bifröst: Start MCP Server (SSE, ${env}, ${role})",
      "type": "shell",
      "command": "uv run grafana-mcp serve --transport sse --env ${env} --role ${role} --port ${port}",
      "group": "build",
      "isBackground": true,
      "presentation": { "panel": "dedicated", "reveal": "always" }
    }
  ]
}`;

  return (
    <div className="guide">
      <div className="guide-header">
        <h2>Use Bifröst in VSCode</h2>
        <p className="muted">
          Wire this Bifröst instance into <strong>Copilot Chat</strong>, <strong>Claude Code</strong>, or any other
          MCP-compatible VSCode extension. The LLM gets all 16 Grafana tools directly in the chat, with role
          enforcement handled by Bifröst.
        </p>
      </div>

      <div className="guide-live">
        <span className="guide-live-label">Live values pulled from this server:</span>
        <span className="badge accent">
          <span className="dot" />
          {sseUrl}
        </span>
        <span className="badge">env: {env}</span>
        <span className="badge">role: {role}</span>
      </div>

      <Step n={1} title="Install an MCP-aware extension">
        <p>
          Pick whichever chat agent you already use — they all support the MCP protocol. Open the VSCode command
          palette (<kbd>⌘⇧P</kbd>) and install one of:
        </p>
        <ul className="ext-list">
          <li>
            <strong>Claude Code</strong> — <code>Extensions: Install Extensions</code> →{" "}
            <code>anthropic.claude-code</code>
          </li>
          <li>
            <strong>GitHub Copilot Chat</strong> — <code>github.copilot-chat</code> (MCP support in v0.22+)
          </li>
          <li>
            <strong>Continue</strong> — <code>continue.continue</code>, also MCP-capable
          </li>
        </ul>
      </Step>

      <Step n={2} title="Make sure Bifröst is running">
        <p>
          In the VSCode terminal or a separate shell (assuming you cloned the repo to <code>~/bifrost</code>):
        </p>
        <CodeBlock lang="bash">
          {`cd ~/bifrost
uv sync
uv run grafana-mcp serve --transport sse --env ${env} --role ${role} --port ${port}`}
        </CodeBlock>
        <Note kind="ok">
          The server should already be running on{" "}
          <code>{serverUrl}</code> if you see live dashboard counts in the Overview tab.
        </Note>
      </Step>

      <Step n={3} title="Create .vscode/mcp.json in your workspace">
        <p>
          Drop this file at the root of any VSCode workspace where you want Grafana access. Extensions auto-discover
          it.
        </p>
        <CodeBlock lang="json">{mcpJson}</CodeBlock>
        <Note>
          Want multiple servers? Add more entries — e.g. one for <code>viewer</code> on port 8765, one for{" "}
          <code>editor</code> on 8767, one for <code>admin</code> on 8766. Each role should be its own Bifröst
          process so the privilege envelope is obvious from <code>lsof</code>.
        </Note>
      </Step>

      <Step n={4} title="(Optional) Add a VSCode task to start it for you">
        <p>
          Save this as <code>.vscode/tasks.json</code> so you can boot the server from <kbd>⌘⇧B</kbd> instead of
          switching to a terminal.
        </p>
        <CodeBlock lang="json">{tasksJson}</CodeBlock>
      </Step>

      <Step n={5} title="Connect from the chat panel">
        <p>In VSCode:</p>
        <ol className="ordered">
          <li>
            Open the command palette → <code>MCP: Connect to Server</code>
          </li>
          <li>
            Pick <strong>bifrost-{env}-{role}</strong>
          </li>
          <li>Open the Copilot Chat / Claude Code panel</li>
          <li>
            The 16 Bifröst tools are now available. Try:
            <div className="sample-prompts">
              <div className="sample-prompt">"List all dashboards tagged executive"</div>
              <div className="sample-prompt">"Which datasources does my Grafana have?"</div>
              <div className="sample-prompt">"Show me the folder hierarchy"</div>
              <div className="sample-prompt">"Are there any firing alerts?"</div>
            </div>
          </li>
        </ol>
      </Step>

      <Step n={6} title="Verify the connection">
        <p>
          In the MCP panel you should see a green "connected" status and a list of 16 tools. If you see "no tools",
          the extension can't reach <code>{sseUrl}</code> — check that the server is running and that no firewall or
          proxy is between VSCode and port {port}.
        </p>
      </Step>

      <div className="guide-footer">
        <h3>Troubleshooting</h3>
        <dl>
          <dt>MCP: Connect to Server isn't in my palette</dt>
          <dd>
            You haven't installed an MCP-capable extension. Install Claude Code or make sure your Copilot Chat is
            on v0.22+.
          </dd>
          <dt>Connection refused</dt>
          <dd>
            The Bifröst server isn't running on the URL in <code>mcp.json</code>. Run{" "}
            <code>curl {serverUrl}/healthz</code> from the same machine.
          </dd>
          <dt>Tool calls return PermissionError</dt>
          <dd>
            The active role is below what the tool needs. <code>silence_alert</code> needs <strong>editor</strong>,{" "}
            <code>list_users</code> needs <strong>admin</strong>. Start a second server on a different port with{" "}
            <code>--role editor</code> or <code>--role admin</code>, and add it to <code>mcp.json</code>.
          </dd>
          <dt>Tool returns stale data</dt>
          <dd>
            Bifröst pools one client per (env, role) pair. Restart the Bifröst process if you've rotated service-
            account tokens externally, or use the Settings drawer in this UI to push updates live.
          </dd>
        </dl>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Python guide
// ─────────────────────────────────────────────────────────────────────────────

export function PythonGuide({ info, serverUrl }: GuideProps) {
  const env = info?.active_environment ?? "dev";
  const role = info?.active_role ?? "viewer";
  const baseUrl = serverUrl;

  const bridgeClient = `"""Minimal Python client for the Bifröst REST bridge.

Requires: httpx>=0.27
Install:  pip install httpx
"""
from __future__ import annotations

import httpx


class BifrostClient:
    def __init__(self, base_url: str = "${baseUrl}") -> None:
        self._http = httpx.Client(base_url=base_url, timeout=30.0)

    def _call(self, path: str) -> dict:
        r = self._http.get(path)
        r.raise_for_status()
        env = r.json()
        if not env.get("ok"):
            raise RuntimeError(f"{env['error']}: {env['message']}")
        return env["data"]

    # ── read helpers ────────────────────────────────────────────
    def server_info(self) -> dict:
        return self._call("/api/server-info")

    def health(self) -> dict:
        return self._call("/api/health")

    def list_dashboards(self, limit: int = 200) -> list[dict]:
        return self._call(f"/api/dashboards?limit={limit}")

    def list_datasources(self) -> list[dict]:
        return self._call("/api/datasources")

    def list_folders(self) -> list[dict]:
        return self._call("/api/folders")

    # ── tool call (generic) ─────────────────────────────────────
    def call_tool(self, name: str, **arguments) -> object:
        r = self._http.post("/api/tools/call", json={"name": name, "arguments": arguments})
        r.raise_for_status()
        env = r.json()
        if not env.get("ok"):
            raise RuntimeError(f"{env['error']}: {env['message']}")
        return env["data"]


if __name__ == "__main__":
    c = BifrostClient()
    info = c.server_info()
    print(f"Bifröst v{info['version']}  env={info['active_environment']}  role={info['active_role']}")

    dashboards = c.list_dashboards()
    print(f"{len(dashboards)} dashboards")

    prod = c.call_tool("list_dashboards", tags=["production"], limit=50)
    print(f"{len(prod)} production dashboards")`;

  const asyncExample = `"""Async example — run many tool calls in parallel."""
from __future__ import annotations

import asyncio
import httpx


async def call_tool(client: httpx.AsyncClient, name: str, **args: object) -> object:
    r = await client.post("/api/tools/call", json={"name": name, "arguments": args})
    r.raise_for_status()
    env = r.json()
    if not env["ok"]:
        raise RuntimeError(f"{env['error']}: {env['message']}")
    return env["data"]


async def main() -> None:
    async with httpx.AsyncClient(base_url="${baseUrl}", timeout=30.0) as http:
        # Fire 3 tools in parallel
        info, health, dashboards = await asyncio.gather(
            call_tool(http, "get_server_info"),
            call_tool(http, "health_check"),
            call_tool(http, "list_dashboards", limit=200),
        )
        print("server:", info)
        print("health:", health)
        print("dashboards:", len(dashboards))


if __name__ == "__main__":
    asyncio.run(main())`;

  const roleSwitch = `"""Switch env/role at runtime via the REST bridge."""
import httpx

http = httpx.Client(base_url="${baseUrl}")

# Switch to editor role so we can call silence_alert
http.post("/api/active", json={"role": "editor"}).raise_for_status()

# Now call a write tool — role enforcement passes
result = http.post(
    "/api/tools/call",
    json={
        "name": "silence_alert",
        "arguments": {
            "matchers": [{"name": "alertname", "value": "HighCPU", "isEqual": True}],
            "duration_minutes": 30,
            "comment": "scheduled maintenance",
        },
    },
).json()

# Flip back to viewer when done
http.post("/api/active", json={"role": "viewer"})`;

  const cliExamples = `# Boot a Bifröst MCP server
grafana-mcp serve --transport sse --env ${env} --role ${role} --port ${info?.transport.port ?? 8765}

# Validate .env without booting the server
grafana-mcp validate-config

# Ping every configured (env, role) pair
grafana-mcp health

# List every registered tool with its minimum role
grafana-mcp list-tools

# Show version
grafana-mcp --version`;

  const envFile = `# ── Active selection ───────────────────────────
GRAFANA_MCP_ACTIVE_ENVIRONMENT=${env}
GRAFANA_MCP_ACTIVE_ROLE=${role}

# ── Transport ──────────────────────────────────
GRAFANA_MCP_TRANSPORT__MODE=sse
GRAFANA_MCP_TRANSPORT__HOST=127.0.0.1
GRAFANA_MCP_TRANSPORT__PORT=${info?.transport.port ?? 8765}

# ── ${env} environment ──────────────────────────
GRAFANA_MCP_ENVIRONMENTS__${env.toUpperCase()}__BASE_URL=http://localhost:3000
GRAFANA_MCP_ENVIRONMENTS__${env.toUpperCase()}__TLS_VERIFY=false
GRAFANA_MCP_ENVIRONMENTS__${env.toUpperCase()}__SERVICE_ACCOUNTS__VIEWER=glsa_xxx
GRAFANA_MCP_ENVIRONMENTS__${env.toUpperCase()}__SERVICE_ACCOUNTS__EDITOR=glsa_yyy
GRAFANA_MCP_ENVIRONMENTS__${env.toUpperCase()}__SERVICE_ACCOUNTS__ADMIN=glsa_zzz`;

  return (
    <div className="guide">
      <div className="guide-header">
        <h2>Use Bifröst from Python</h2>
        <p className="muted">
          Drop Bifröst into scripts, notebooks, and CI. Two patterns: talk to the REST bridge for quick scripts, or
          install the MCP server as a CLI and run it as a long-lived service for agents to consume.
        </p>
      </div>

      <div className="guide-live">
        <span className="guide-live-label">Live values pulled from this server:</span>
        <span className="badge accent">
          <span className="dot" />
          {baseUrl}
        </span>
        <span className="badge">env: {env}</span>
        <span className="badge">role: {role}</span>
      </div>

      <Step n={1} title="Prerequisites">
        <ul className="ext-list">
          <li>Python 3.11+ (<code>python --version</code>)</li>
          <li>
            <a href="https://docs.astral.sh/uv/" target="_blank" rel="noreferrer">uv</a> or pip for installing
            packages
          </li>
          <li>A running Bifröst MCP server (this page targets <code>{baseUrl}</code>)</li>
          <li>For server-side: Grafana 9.x–12.x reachable + three service-account tokens</li>
        </ul>
      </Step>

      <Step n={2} title="Option A — Quick scripts via the REST bridge">
        <p>
          The fastest way to drive Bifröst from Python: use the REST bridge exposed at <code>/api/*</code> alongside
          the MCP transport. Every call lands on the same typed tool function (with role enforcement, pooling, and
          retry) that an MCP client would invoke.
        </p>
        <p>
          <strong>Install:</strong>
        </p>
        <CodeBlock lang="bash">{`pip install httpx
# or
uv pip install httpx`}</CodeBlock>
        <p>
          <strong>A tiny synchronous client:</strong>
        </p>
        <CodeBlock lang="python">{bridgeClient}</CodeBlock>
        <Note kind="ok">
          Save as <code>bifrost_client.py</code> and run <code>python bifrost_client.py</code> — you should see the
          count of dashboards currently in Grafana.
        </Note>
      </Step>

      <Step n={3} title="Async for parallel tool calls">
        <p>
          Bifröst is async end-to-end — the REST bridge handles concurrent calls cleanly. Use{" "}
          <code>httpx.AsyncClient</code> + <code>asyncio.gather</code> when you want to fan out.
        </p>
        <CodeBlock lang="python">{asyncExample}</CodeBlock>
      </Step>

      <Step n={4} title="Runtime env / role switching">
        <p>
          Switch env or role mid-session via <code>POST /api/active</code>. Bifröst evicts the cached pool clients
          and rebuilds with the new tokens on the next call.
        </p>
        <CodeBlock lang="python">{roleSwitch}</CodeBlock>
        <Note kind="warn">
          Elevating to <strong>editor</strong> or <strong>admin</strong> only works if the Bifröst server was
          started with a matching <code>--role</code> ceiling. You can't escalate past the server's max.
        </Note>
      </Step>

      <Step n={5} title="Option B — Install grafana-mcp as a CLI">
        <p>
          If you want Bifröst itself (not just the bridge), clone the repo and install in dev mode. You get the{" "}
          <code>grafana-mcp</code> CLI plus all 16 typed MCP tools as importable Python modules.
        </p>
        <CodeBlock lang="bash">{`git clone https://github.com/gpadidala/bifrost.git
cd bifrost
cd packages/core
uv venv
uv pip install -e ".[dev]"
# 'grafana-mcp' is now on your PATH`}</CodeBlock>
      </Step>

      <Step n={6} title="Configure the server with .env">
        <p>
          Drop this at the repo root. The <code>__</code> delimiter reaches into nested Pydantic fields.
        </p>
        <CodeBlock lang="bash">{envFile}</CodeBlock>
        <Note>
          Generate Grafana service-account tokens in{" "}
          <strong>Administration → Service Accounts</strong>. Create three: <code>bifrost-{env}-viewer</code>,{" "}
          <code>bifrost-{env}-editor</code>, <code>bifrost-{env}-admin</code>, each with the matching Grafana RBAC
          role.
        </Note>
      </Step>

      <Step n={7} title="CLI reference">
        <CodeBlock lang="bash">{cliExamples}</CodeBlock>
      </Step>

      <Step n={8} title="Import tools directly in Python">
        <p>
          If you want to embed Bifröst in a long-running Python app (a cron, a scheduler, a CI gate), import the
          tool functions directly instead of going through HTTP.
        </p>
        <CodeBlock lang="python">{`import asyncio
from grafana_mcp._state import init as init_state
from grafana_mcp.client.pool import ClientPool
from grafana_mcp.settings import Settings
from grafana_mcp.tools import dashboards, utility


async def main() -> None:
    settings = Settings()        # reads .env
    pool = ClientPool(settings)
    init_state(settings, pool)

    info = await utility.get_server_info()
    print("connected:", info)

    prod_dashboards = await dashboards.list_dashboards(tags=["production"], limit=50)
    for d in prod_dashboards:
        print(f"  • {d.title}  ({d.uid})")

    await pool.close_all()


asyncio.run(main())`}</CodeBlock>
      </Step>

      <div className="guide-footer">
        <h3>Which pattern should I use?</h3>
        <dl>
          <dt>REST bridge (Option A)</dt>
          <dd>
            One-off scripts, notebooks, CI checks, short-lived jobs. Needs only <code>httpx</code>. Fast to
            iterate.
          </dd>
          <dt>grafana-mcp CLI (Option B)</dt>
          <dd>
            Running Bifröst as a long-lived service for agents (VSCode, Claude Code) to consume, or embedding in a
            larger Python app where you want typed tool functions.
          </dd>
          <dt>Direct tool imports (Step 8)</dt>
          <dd>
            You're writing a Python app that wants type safety, in-process calls (zero HTTP overhead), and the full
            Pydantic contract. Requires <code>grafana-mcp</code> installed in the same venv.
          </dd>
        </dl>
      </div>
    </div>
  );
}
