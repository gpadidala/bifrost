# First Run Walkthrough

This page is the guided tour: from a fresh `git clone` to your first AI-driven Grafana question, with screenshots and the things people usually trip on.

## 0. Generate three Grafana service-account tokens

Bifröst needs **three tokens per environment**, one for each Grafana RBAC role. In Grafana:

1. **Administration → Service accounts → Add service account**
2. Name it `bifrost-viewer`, role `Viewer`. Click **Create**.
3. On the service account page → **Add token** → name `bifrost-token` → no expiry (or your org's policy) → **Generate**.
4. **Copy the `glsa_...` value** — Grafana shows it once and only once.
5. Repeat steps 1-4 for `bifrost-editor` (role `Editor`) and `bifrost-admin` (role `Admin`).

You now have three tokens for one environment. Repeat for any other environments you want to wire up.

> 💡 **Token naming convention.** We name service accounts `bifrost-<role>` so that Grafana audit logs make it obvious *which* MCP role made a given write. If you skip this, every audit entry just says "service account" and you lose the ability to trace a misbehaving tool back to a role.

## 1. Clone and configure

```bash
git clone https://github.com/gpadidala/bifrost.git
cd bifrost
cp .env.example .env
$EDITOR .env
```

Fill in your `dev` block first — it's the safest place to make mistakes:

```env
GRAFANA_MCP_ACTIVE_ENVIRONMENT=dev
GRAFANA_MCP_ACTIVE_ROLE=viewer

GRAFANA_MCP_ENVIRONMENTS__DEV__BASE_URL=http://localhost:3000
GRAFANA_MCP_ENVIRONMENTS__DEV__TLS_VERIFY=false
GRAFANA_MCP_ENVIRONMENTS__DEV__SERVICE_ACCOUNTS__VIEWER=glsa_xxx
GRAFANA_MCP_ENVIRONMENTS__DEV__SERVICE_ACCOUNTS__EDITOR=glsa_yyy
GRAFANA_MCP_ENVIRONMENTS__DEV__SERVICE_ACCOUNTS__ADMIN=glsa_zzz
```

You **must** also fill in `perf` and `prod` placeholder blocks (or delete them) — Pydantic will refuse to boot if `active_environment` references a missing block, but it won't complain about other blocks being absent.

## 2. Validate before booting

```bash
uv sync
uv run grafana-mcp validate-config
```

Expected output:

```
✓ Loaded settings from .env
✓ Active environment: dev
✓ Active role: viewer
✓ Pinging dev/viewer  → ok (12 ms)
✓ Pinging dev/editor  → ok (14 ms)
✓ Pinging dev/admin   → ok (13 ms)

All environments healthy.
```

If any role shows `✗ 401`, that token is wrong or revoked. If you see `✗ connection refused`, your `BASE_URL` is wrong or Grafana isn't running.

## 3. Boot the server

```bash
uv run grafana-mcp serve --transport sse --env dev --role viewer --port 8765
```

You'll see a few startup log lines, then:

```
✓ Bifröst MCP server listening on http://0.0.0.0:8765/mcp/sse
```

Leave this terminal open. Every tool call will log here in real time, which is great for the first 10 minutes when you want to see what the LLM is actually doing.

## 4. Boot the React UI

```bash
pnpm --filter ./packages/ui dev
# → http://localhost:5173
```

Open the URL. The first screen is **Connection Config**.

![Connection Config](../assets/screenshots/walkthrough-01-connection.png)

The `dev` card should already say **Connected** in green — the UI auto-discovered the server you just started. The `perf` and `prod` cards are red **Untested** until you click **Test Connection** on each.

## 5. Set your LLM key

Click the **gear** icon in the top-right → **LLM Settings** drawer slides in.

![LLM Drawer](../assets/screenshots/walkthrough-02-llm.png)

- **Provider:** Anthropic or OpenAI
- **Model:** `claude-sonnet-4-20250514` is a reliable default; for cheaper Q&A try `gpt-4o-mini`.
- **API key:** paste it in. The key is stored in `localStorage` (encrypted with your passphrase if you set one) and goes **directly from the browser to Anthropic/OpenAI** — Bifröst never sees it.
- **System prompt:** the default is tuned for Grafana Q&A. Edit it if you want a different tone.

Click **Save**.

## 6. Your first AI tool call

Click **Chat** in the sidebar. Type:

> List all the dashboards in the General folder.

You'll see the LLM response stream in. About a second in, a collapsible card appears mid-stream:

![Tool Call Card](../assets/screenshots/walkthrough-03-toolcall.png)

This is the **tool call visualization** — it shows the tool name (`list_dashboards`), the params the LLM chose (`{"folder_uid": "general"}`), and the result (a JSON list). Click the card to expand/collapse.

The LLM then continues its response with a natural-language summary of the dashboards.

In the terminal where the MCP server is running, you'll see matching log lines:

```
{"event":"tool.call","tool":"list_dashboards","params":{"folder_uid":"general"},"role":"viewer"}
{"event":"grafana.request","method":"GET","path":"/api/search","status":200,"latency_ms":34}
{"event":"tool.result","tool":"list_dashboards","count":7}
```

## 7. Try a write — the role enforcement moment

With the server still running on `--role viewer`, ask:

> Silence the high-cpu alert for 30 minutes.

The LLM will pick the `silence_alert` tool, call it, and Bifröst will respond with:

```json
{
  "error": "PermissionError",
  "message": "Tool 'silence_alert' requires role 'editor', got 'viewer'"
}
```

The LLM relays the error in plain English. **Stop the server** (Ctrl-C), restart with `--role editor`:

```bash
uv run grafana-mcp serve --transport sse --env dev --role editor --port 8765
```

Refresh the UI, run the same prompt — this time it succeeds. The role badge in the UI header will have flipped from **VIEWER** to **EDITOR**.

This is the entire RBAC story: roles are explicit, mismatches fail fast, and the LLM never gets a chance to do something it didn't ask for permission to do.

## 8. Where to go next

- **[Configuration Reference](configuration.md)** — every env var
- **[MCP Tool Catalog](../features/mcp-tools.md)** — every tool, every parameter
- **[AI Chat](../features/ai-chat.md)** — how the LLM ↔ MCP loop works under the hood
- **[Python SDK](../packages/sdk.md)** — drop-in for notebooks and CI

If something didn't work, head to [Troubleshooting](../guides/troubleshooting.md) — the top 5 issues and their fixes are documented.
