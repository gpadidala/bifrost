# MCP Tool Catalog

Bifröst exposes ~20 typed tools to any MCP client (VSCode, Claude Code, Cursor, Cline, the Bifröst UI, the Python SDK). Every tool is grouped by Grafana resource and tagged with a minimum role.

For the full input/output schemas, see [MCP Tools Reference](../api/mcp-tools-reference.md).

## At a glance

| Group | Tools | Min role |
|---|---|---|
| 📊 [Dashboards](#dashboards) | `list_dashboards` · `get_dashboard` · `search_dashboards` · `get_dashboard_panels` | viewer |
| 🔌 [Datasources](#datasources) | `list_datasources` · `get_datasource` · `query_datasource` | viewer |
| 🔔 [Alerts (read)](#alerts-read) | `list_alert_rules` · `get_alert_rule` · `list_alert_instances` | viewer |
| 🔕 [Alerts (write)](#alerts-write) | `silence_alert` | **editor** |
| 📁 [Folders](#folders) | `list_folders` | viewer |
| 👥 [Users & Org](#users--org) | `list_users` · `list_service_accounts` | **admin** |
| 💚 [Utility](#utility) | `health_check` · `get_server_info` | viewer |

## Dashboards

### `list_dashboards`

List dashboards, optionally filtered by folder UID and tags.

```python
list_dashboards(
    folder_uid: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
) -> list[DashboardSummary]
```

Returns one entry per dashboard with: `uid`, `title`, `folder_title`, `folder_uid`, `tags`, `url`, `type`. Backed by Grafana's `/api/search?type=dash-db`.

### `get_dashboard`

Fetch one dashboard by UID, including its full panel definitions.

```python
get_dashboard(uid: str) -> DashboardDetail
```

Returns: dashboard metadata (`title`, `description`, `tags`, `version`, `created_by`, `updated_by`), `meta` (folder, permissions, slug), and the full `panels` list.

### `search_dashboards`

Full-text search across dashboards. Wraps `/api/search?query=...&type=dash-db`.

```python
search_dashboards(query: str, type: Literal["dash-db", "dash-folder"] = "dash-db") -> list[SearchResult]
```

### `get_dashboard_panels`

Convenience wrapper around `get_dashboard` that returns just the panel list, flattened. Useful when you only care about the panels (e.g., "list every panel that uses the prometheus datasource").

```python
get_dashboard_panels(uid: str) -> list[Panel]
```

## Datasources

### `list_datasources`

```python
list_datasources() -> list[DatasourceSummary]
```

Returns `uid`, `name`, `type`, `url`, `is_default`, `access` for each datasource.

### `get_datasource`

```python
get_datasource(uid: str) -> DatasourceDetail
```

Adds `json_data`, `secure_json_fields`, `version`, `read_only`, `with_credentials` to the summary.

### `query_datasource`

Run a query against a datasource. Useful for "show me the current value of `up{job=foo}`" without leaving the LLM.

```python
query_datasource(
    datasource_uid: str,
    query: str,
    time_range: TimeRange,
) -> QueryResult
```

`TimeRange` is `{"from": ISO8601, "to": ISO8601}`. The query string is interpreted by the datasource (PromQL for Prometheus, LogQL for Loki, TraceQL for Tempo, SQL for SQL datasources).

`QueryResult` is a typed wrapper around Grafana's `/api/ds/query` response, with `frames`, `errors`, and `status`.

## Alerts (read)

### `list_alert_rules`

```python
list_alert_rules(folder_uid: str | None = None) -> list[AlertRule]
```

Returns alert rules optionally scoped to one folder. Each rule has `uid`, `title`, `condition`, `query`, `intervals`, `labels`, `annotations`, `state`.

### `get_alert_rule`

```python
get_alert_rule(uid: str) -> AlertRuleDetail
```

Adds `version`, `created`, `updated`, `provenance`, full notification policy bindings.

### `list_alert_instances`

```python
list_alert_instances(state: Literal["firing", "normal", "pending", "no_data"] | None = None) -> list[AlertInstance]
```

Returns the *current* state of alert instances. Backed by `/api/alertmanager/grafana/api/v2/alerts`.

## Alerts (write)

### `silence_alert` (editor)

Create a silence for a matcher.

```python
silence_alert(
    matcher: str,                # e.g. '{job="api", severity="warning"}'
    duration_minutes: int,
    comment: str,
) -> Silence
```

Returns the created `Silence` with its UID. Requires **`editor`** role.

## Folders

### `list_folders`

```python
list_folders() -> list[Folder]
```

Returns the folder list with `uid`, `title`, `parent_uid`, `url`, `has_acl`. Useful as the first call when navigating dashboards.

## Users & Org

### `list_users` (admin)

```python
list_users() -> list[UserSummary]
```

Lists org users: `id`, `email`, `login`, `name`, `role`, `is_admin`, `last_seen`. Requires **`admin`** role.

### `list_service_accounts` (admin)

```python
list_service_accounts() -> list[ServiceAccount]
```

Lists Grafana service accounts: `id`, `name`, `login`, `role`, `tokens` (count, not values), `is_disabled`. Requires **`admin`** role.

## Utility

### `health_check`

```python
health_check(environment: Literal["dev", "perf", "prod"] | None = None) -> HealthStatus
```

Pings the Grafana `/api/health` endpoint for the given env (defaults to active). Returns `{"status": "ok" | "error", "version": "...", "commit": "...", "database": "ok", "latency_ms": 12}`.

### `get_server_info`

```python
get_server_info() -> ServerInfo
```

Returns Bifröst's own state — version, transport mode, active env, active role, uptime seconds, registered tool count. Useful for the LLM to introspect what it's connected to before making decisions.

## How the LLM picks tools

The MCP protocol gives the LLM the tool catalog as part of the conversation context — names, descriptions, input schemas. The LLM picks one based on:

1. The user's question
2. The tool description (your docstring)
3. The input schema (Pydantic-generated)

This is why **docstrings are load-bearing** in core. A tool with a vague docstring gets picked at the wrong times. The convention in `packages/core/src/grafana_mcp/tools/` is:

```python
@mcp.tool()
async def silence_alert(matcher: str, duration_minutes: int, comment: str) -> Silence:
    """Silence Grafana alerts matching the given label matcher for N minutes.

    Use this when the user wants to suppress notifications for known issues
    (deploys, planned maintenance, flapping alerts). Requires the editor role.

    The matcher is a Grafana label-matcher string like '{job="api", severity="warning"}'.
    """
```

The first sentence is the one the LLM relies on most. Keep it action-oriented and unambiguous.
