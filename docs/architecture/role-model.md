# Role Model & RBAC

The single biggest risk in "let an LLM drive Grafana" is letting the LLM run with admin tokens by accident. Bifröst's role model is the smallest possible safety net: **three explicit roles, three explicit tokens per environment, and one fail-fast lookup table.**

## The hierarchy

```python
ROLE_HIERARCHY = {
    "viewer": 0,
    "editor": 1,
    "admin":  2,
}
```

Strict ordering. `admin > editor > viewer`. A higher role can call any tool a lower role can; the reverse is impossible.

## The three tokens

Every environment in Bifröst holds **three Grafana service-account tokens**, one per role:

```python
class ServiceAccountSet(BaseModel):
    viewer: SecretStr   # Grafana role: Viewer
    editor: SecretStr   # Grafana role: Editor
    admin:  SecretStr   # Grafana role: Admin
```

These are **separate Grafana service accounts**, each created with the matching Grafana RBAC role in the Grafana UI. They are **not** the same token reused — they have different glsa values, different audit-log identities, and different RBAC permissions enforced *by Grafana itself*.

This means even if Bifröst had a bug and accidentally sent a write request with the viewer token, **Grafana would reject it**. The role enforcement in Bifröst is defense in depth — Grafana's own RBAC is the bottom layer.

## Per-tool minimum roles

Every tool is tagged with a minimum required role. The default is `viewer`:

```python
TOOL_MINIMUM_ROLE: dict[str, Literal["viewer", "editor", "admin"]] = {
    # Read tools — viewer is enough (default, listed for clarity)
    "list_dashboards":       "viewer",
    "get_dashboard":         "viewer",
    "search_dashboards":     "viewer",
    "get_dashboard_panels":  "viewer",
    "list_datasources":      "viewer",
    "get_datasource":        "viewer",
    "query_datasource":      "viewer",
    "list_alert_rules":      "viewer",
    "get_alert_rule":        "viewer",
    "list_alert_instances":  "viewer",
    "list_folders":          "viewer",
    "health_check":          "viewer",
    "get_server_info":       "viewer",

    # Write tools — editor required
    "silence_alert":         "editor",

    # Org/user tools — admin required
    "list_users":            "admin",
    "list_service_accounts": "admin",
}
```

This table is the **single source of truth**. It lives in `packages/core/src/grafana_mcp/rbac.py`. CI runs a check that every `@mcp.tool()` registered in core has either an explicit entry here or a comment confirming `viewer` is intentional — no silent defaults for new tools.

## Enforcement

```python
async def enforce_role(tool_name: str, active_role: str) -> None:
    required = TOOL_MINIMUM_ROLE.get(tool_name, "viewer")
    if ROLE_HIERARCHY[active_role] < ROLE_HIERARCHY[required]:
        raise PermissionError(
            f"Tool '{tool_name}' requires role '{required}', got '{active_role}'"
        )
```

This middleware runs **before** the tool function is invoked. The HTTP call to Grafana never happens if the role is insufficient. The error is raised, logged, and returned to the MCP client as a structured error response — the LLM gets to see "you need editor for this" and can try to recover (e.g., ask the user for permission).

## How the active role is chosen

In order of precedence:

1. **Per-call override** in the MCP tool call context (`role` parameter on the tool input). The MCP client can pass `{"role": "editor"}` to elevate one specific call. The override is bounded by the server's `--role` flag — you can't elevate above what the server was started with.
2. **Server default** from `--role` CLI flag or `GRAFANA_MCP_ACTIVE_ROLE` env var.
3. **`viewer`** as the absolute floor.

> ⚠️ **The server's `--role` flag is the *ceiling*, not the *floor*.** If you start the server with `--role editor`, individual tool calls can run as `viewer` or `editor`, but never as `admin`. The only way to call admin tools is to start a server with `--role admin`. This is intentional — it makes the server's privilege envelope obvious from the command line.

## Recommended deployment pattern

Run **separate server processes per role** so each process has the smallest privilege envelope it needs:

```bash
# Terminal 1 — read-only, used by 90% of agents
uv run grafana-mcp serve --transport sse --env prod --role viewer --port 8765

# Terminal 2 — write-capable, used by on-call automation
uv run grafana-mcp serve --transport sse --env prod --role editor --port 8767

# Terminal 3 — admin, used by humans only, fronted by a higher-auth proxy
uv run grafana-mcp serve --transport sse --env prod --role admin --port 8766
```

Then in `.vscode/mcp.json` (or your agent's config), wire up three separate MCP servers — `grafana-prod-viewer`, `grafana-prod-editor`, `grafana-prod-admin` — and let users explicitly pick which one to connect to. The role appears in the server label so it's never ambiguous.

This is how the [VSCode integration](../deployment/vscode.md) is set up by default.

## Auditability

Because each role uses a *different* Grafana service account, every Grafana audit log entry tells you which Bifröst role made the request:

```
service_account=bifrost-prod-editor  user_id=42  action=alerting.silences.create
```

You can query Grafana's audit logs by service account to see exactly what each role has been doing in production. This is the second reason to name the service accounts `bifrost-<env>-<role>` — the [first-run guide](../getting-started/first-run.md#0-generate-three-grafana-service-account-tokens) walks through it.

## What about read-write isolation per environment?

The same three-role model applies independently to every environment. The `dev/admin` token cannot do anything to `prod`, because it's a different token in a different Grafana. Environment isolation and role isolation are orthogonal — you get both for free as long as you create separate service accounts in each Grafana cluster.

## Adding a new role?

**Don't.** Three roles match Grafana's RBAC and three is the most a human can keep in their head. If you find yourself wanting a fourth (e.g., "alerting-editor"), the right fix is to model that as a *separate environment* — a different Grafana org or instance — not a fourth role. The literal type system enforces this:

```python
Role = Literal["viewer", "editor", "admin"]
```

Adding a value here would require updating the table, every CLI flag, every UI selector, and every test. That friction is intentional.
