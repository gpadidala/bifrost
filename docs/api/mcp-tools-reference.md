# MCP Tools Reference

The complete typed API for every Bifröst MCP tool — input schema, output schema, error envelope, and an example call as MCP JSON-RPC.

For the high-level catalog grouped by feature, see [MCP Tool Catalog](../features/mcp-tools.md).

## Common types

```python
EnvName = Literal["dev", "perf", "prod"]
GrafanaRole = Literal["viewer", "editor", "admin"]

class TimeRange(BaseModel):
    from_: datetime = Field(alias="from")   # ISO8601
    to: datetime                             # ISO8601

class ErrorEnvelope(BaseModel):
    error: str          # exception class name, e.g. "PermissionError"
    message: str        # human-readable
    tool: str           # which tool raised
    role: GrafanaRole   # active role at time of error
    environment: EnvName
```

Every tool can also accept these two **keyword-only** overrides:

```python
environment: EnvName | None = None  # override active env for this call
role: GrafanaRole | None = None     # override active role (bounded by server ceiling)
```

These are present on every tool's schema but omitted from the per-tool docs below for brevity.

---

## Dashboards

### `list_dashboards`

```python
async def list_dashboards(
    folder_uid: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
) -> list[DashboardSummary]
```

**Min role:** `viewer`

**Output:**

```python
class DashboardSummary(BaseModel):
    uid: str
    title: str
    type: Literal["dash-db", "dash-folder"]
    url: str
    folder_uid: str | None
    folder_title: str | None
    tags: list[str]
    is_starred: bool
```

**Example MCP call:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "list_dashboards",
    "arguments": { "tags": ["production"], "limit": 50 }
  }
}
```

### `get_dashboard`

```python
async def get_dashboard(uid: str) -> DashboardDetail
```

**Min role:** `viewer`

**Output:**

```python
class DashboardDetail(BaseModel):
    uid: str
    title: str
    description: str | None
    tags: list[str]
    version: int
    schema_version: int
    panels: list[Panel]
    templating: TemplatingConfig
    time: TimeRange
    refresh: str | None
    meta: DashboardMeta
```

### `search_dashboards`

```python
async def search_dashboards(
    query: str,
    type: Literal["dash-db", "dash-folder"] = "dash-db",
) -> list[SearchResult]
```

**Min role:** `viewer`

### `get_dashboard_panels`

```python
async def get_dashboard_panels(uid: str) -> list[Panel]
```

**Min role:** `viewer`

```python
class Panel(BaseModel):
    id: int
    title: str
    type: str                    # graph, timeseries, stat, gauge, table, ...
    datasource: DatasourceRef
    targets: list[QueryTarget]
    grid_pos: GridPos
    options: dict[str, Any]
```

---

## Datasources

### `list_datasources`

```python
async def list_datasources() -> list[DatasourceSummary]
```

**Min role:** `viewer`

```python
class DatasourceSummary(BaseModel):
    uid: str
    name: str
    type: str                    # prometheus, loki, tempo, mimir, postgres, mysql, ...
    url: str
    is_default: bool
    access: Literal["proxy", "direct"]
```

### `get_datasource`

```python
async def get_datasource(uid: str) -> DatasourceDetail
```

**Min role:** `viewer`

```python
class DatasourceDetail(DatasourceSummary):
    json_data: dict[str, Any]
    secure_json_fields: dict[str, bool]   # field names only, never values
    version: int
    read_only: bool
    with_credentials: bool
```

### `query_datasource`

```python
async def query_datasource(
    datasource_uid: str,
    query: str,
    time_range: TimeRange,
) -> QueryResult
```

**Min role:** `viewer`

```python
class QueryResult(BaseModel):
    frames: list[DataFrame]
    errors: list[QueryError]
    status: Literal["ok", "error", "partial"]

class DataFrame(BaseModel):
    name: str
    fields: list[Field]
    length: int

class Field(BaseModel):
    name: str
    type: str                    # number, time, string, boolean
    values: list[Any]
    labels: dict[str, str]
```

---

## Alerts

### `list_alert_rules`

```python
async def list_alert_rules(folder_uid: str | None = None) -> list[AlertRule]
```

**Min role:** `viewer`

```python
class AlertRule(BaseModel):
    uid: str
    title: str
    folder_uid: str
    rule_group: str
    condition: str
    interval_seconds: int
    no_data_state: Literal["NoData", "Alerting", "OK"]
    exec_err_state: Literal["Alerting", "Error", "OK"]
    state: Literal["normal", "pending", "firing", "no_data", "error"]
    labels: dict[str, str]
    annotations: dict[str, str]
```

### `get_alert_rule`

```python
async def get_alert_rule(uid: str) -> AlertRuleDetail
```

**Min role:** `viewer`

```python
class AlertRuleDetail(AlertRule):
    version: int
    created: datetime
    updated: datetime
    provenance: Literal["api", "file", "ui"] | None
    data: list[QueryStage]            # the actual query graph
```

### `list_alert_instances`

```python
async def list_alert_instances(
    state: Literal["firing", "normal", "pending", "no_data"] | None = None,
) -> list[AlertInstance]
```

**Min role:** `viewer`

```python
class AlertInstance(BaseModel):
    fingerprint: str
    rule_uid: str
    rule_title: str
    state: Literal["firing", "normal", "pending", "no_data", "error"]
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: datetime
    ends_at: datetime | None
    value: float | None
```

### `silence_alert`

```python
async def silence_alert(
    matcher: str,                    # e.g. '{job="api", severity="warning"}'
    duration_minutes: int,
    comment: str,
) -> Silence
```

**Min role:** `editor`

```python
class Silence(BaseModel):
    uid: str
    matchers: list[Matcher]
    starts_at: datetime
    ends_at: datetime
    comment: str
    created_by: str
    status: Literal["active", "expired", "pending"]
```

**Example error (called with viewer role):**

```json
{
  "error": "PermissionError",
  "message": "Tool 'silence_alert' requires role 'editor', got 'viewer'",
  "tool": "silence_alert",
  "role": "viewer",
  "environment": "prod"
}
```

---

## Folders

### `list_folders`

```python
async def list_folders() -> list[Folder]
```

**Min role:** `viewer`

```python
class Folder(BaseModel):
    uid: str
    title: str
    parent_uid: str | None
    url: str
    has_acl: bool
    can_admin: bool
    can_edit: bool
    can_save: bool
```

---

## Users & Org

### `list_users`

```python
async def list_users() -> list[UserSummary]
```

**Min role:** `admin`

```python
class UserSummary(BaseModel):
    id: int
    email: str
    login: str
    name: str
    role: Literal["Viewer", "Editor", "Admin"]
    is_admin: bool
    last_seen_at: datetime | None
    is_disabled: bool
```

### `list_service_accounts`

```python
async def list_service_accounts() -> list[ServiceAccount]
```

**Min role:** `admin`

```python
class ServiceAccount(BaseModel):
    id: int
    name: str
    login: str
    role: Literal["Viewer", "Editor", "Admin"]
    is_disabled: bool
    tokens: int                     # token COUNT, not values
    created_at: datetime
```

> 🔐 Bifröst **never** returns service-account token values, even to admin callers. The `tokens` field is a count.

---

## Utility

### `health_check`

```python
async def health_check(environment: EnvName | None = None) -> HealthStatus
```

**Min role:** `viewer`

```python
class HealthStatus(BaseModel):
    status: Literal["ok", "error"]
    version: str | None             # Grafana version, e.g. "11.4.0"
    commit: str | None
    database: Literal["ok", "error"] | None
    latency_ms: int
    environment: EnvName
    error: str | None
```

### `get_server_info`

```python
async def get_server_info() -> ServerInfo
```

**Min role:** `viewer`

```python
class ServerInfo(BaseModel):
    bifrost_version: str
    transport: Literal["sse", "http"]
    active_environment: EnvName
    active_role: GrafanaRole
    uptime_seconds: int
    tool_count: int
    grafana_version: str | None
    python_version: str
```

---

## Error envelopes

Every tool can return any of these error classes:

| Class | When | HTTP equivalent |
|---|---|---|
| `PermissionError` | Active role below tool's minimum | 403 |
| `GrafanaError` | Grafana returned 4xx/5xx after retries | 4xx/5xx |
| `ValidationError` | Grafana response didn't match Pydantic schema | 502 |
| `ConnectionError` | Couldn't reach Grafana (DNS, TLS, refused) | 503 |
| `TimeoutError` | Request exceeded `timeout_seconds` | 504 |
| `RateLimitError` | Local semaphore queue is full *and* the call timed out waiting | 429 |

The MCP client receives these as a JSON-RPC error response with the envelope above as the `error.data` field.

## How the schemas are generated

Every Pydantic model in `packages/core/src/grafana_mcp/schemas/` becomes:

1. An **MCP tool input schema** (JSON Schema) — emitted by the MCP SDK at server startup
2. An **MCP tool output schema** — emitted alongside the input schema
3. A **TypeScript type** in `packages/ui/src/types/generated.ts` — emitted by `make codegen` (uses `pydantic-to-typescript`)
4. The **Python SDK method signature** — imported directly from the shared `_schemas/` module

This is why you can change a single Pydantic field and have the change land in the server, the UI types, and the SDK in one go. **The schema is the contract.**
