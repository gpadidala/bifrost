# Grafana Resource Explorer

The Resource Explorer is the left-side panel of the chat UI: a live, lazy-loaded tree of folders → dashboards → panels, plus flat lists of datasources and alert rules. Everything in the panel is fetched via MCP tool calls — there's no separate Grafana API integration.

## Layout

```
┌──────────────── Explorer ────────────────┐
│ ▾ 📁 Folders                              │
│   ▾ General                               │
│     ▸ API Health           (12 panels)    │
│     ▸ Postgres Overview    (8 panels)     │
│     ▸ Kafka                (5 panels)     │
│   ▸ Production                            │
│   ▸ Staging                               │
│                                           │
│ ▾ 🔌 Datasources                          │
│   ● Prometheus  prometheus-prod           │
│   ● Loki        loki-prod                 │
│   ● Tempo       tempo-prod                │
│   ● Mimir       mimir-prod                │
│   ● PostgreSQL  reporting-db              │
│                                           │
│ ▾ 🔔 Alert Rules (47)                     │
│   🔥 General                              │
│     ⚠ HighCPU              firing         │
│     ⚠ HighMemory           firing         │
│   ▸ Production                            │
│   ▸ Staging                               │
│                                           │
└───────────────────────────────────────────┘
```

## How it loads

The explorer is **lazy** — nothing is fetched until you expand a section. The fetch sequence is:

1. **On first mount** — fires `list_folders()` and `list_datasources()` in parallel. The folder list and datasource list render.
2. **On folder expand** — fires `list_dashboards(folder_uid=...)` for that folder. The dashboards render under it.
3. **On dashboard expand** — fires `get_dashboard_panels(uid=...)` for that dashboard. The panel list renders under it.
4. **On the Alerts section expand** — fires `list_alert_rules()` (cached for 30s) and groups by folder.

Every fetch goes through TanStack Query, so:

- Results are cached and reused across re-renders
- Stale data is shown while refetching (no flash of empty state)
- Errors are surfaced as inline ⚠ icons next to the failed node

## Status badges

### Datasources

Each datasource has a colored dot — green if `health_check`-style ping succeeded, red if not. Click the dot to re-test.

### Alert rules

Each alert rule has a state badge:

| Badge | Meaning |
|---|---|
| 🔥 firing | At least one instance is firing |
| 🟡 pending | Pending evaluation |
| 🟢 normal | All instances normal |
| ⚪ no_data | Insufficient data |

Folders aggregate their children — a folder's badge shows the most severe state across its rules.

## "Ask AI about this" actions

Every node in the tree has a hover action: a small chat-bubble icon. Clicking it:

1. Generates a structured **context card** for that node
2. Drops the card into the chat input area
3. Focuses the input

The context card format depends on the node type:

| Node | Context card |
|---|---|
| Folder | `[Context: folder "Production" (uid=abc, 12 dashboards)]` |
| Dashboard | `[Context: dashboard "API Health" (uid=xyz, 12 panels, refs prometheus-prod + loki-prod)]` |
| Panel | `[Context: panel "p99 latency" (id=4, query=histogram_quantile(...), datasource=prometheus-prod)]` |
| Datasource | `[Context: datasource "prometheus-prod" (uid=abc, type=prometheus, url=http://...)]` |
| Alert rule | `[Context: alert "HighCPU" (uid=def, state=firing, condition=avg(cpu) > 0.9)]` |

The user types their question after the card and hits send:

```
[Context: dashboard "API Health" (uid=xyz, 12 panels, refs prometheus-prod + loki-prod)]
What's the most expensive panel in this dashboard?
```

The LLM gets the context card as part of the message, knows the UID, and can call `get_dashboard(uid="xyz")` directly without searching.

## Drag-and-drop

Dashboards and panels are draggable. You can drag them into the chat input to drop the same context card without using the hover action. Useful for keyboard-light navigation.

## Refresh

A small ↻ button at the top of each section forces a refetch and busts the TanStack Query cache for that subtree. Useful when you've just edited something in Grafana directly and want to see the change.

## Filtering

A search input at the top of the explorer panel does client-side filtering across all loaded nodes. It's a substring match on names + UIDs + tags. Filter highlights matching nodes and dims the rest. Clear with `Esc`.

For *server-side* search (which finds dashboards you haven't loaded yet), use the chat: ask "find all dashboards tagged kafka" and the LLM will fire `search_dashboards`.

## Performance notes

- The folder list typically returns ~10-50 entries and is fetched once per session.
- The datasource list is similar — fetched once.
- Dashboards-per-folder can be hundreds. The render uses windowed virtualization (`@tanstack/react-virtual`) once a folder has more than 30 children.
- Panel lists are usually under 30, so no virtualization is needed there.
- Alert rules can be in the thousands. The list is virtualized and refetched on a 30-second cadence.

If you have a Grafana with thousands of dashboards in one folder, the lazy load handles it fine — but the initial folder expand may take a second or two. The skeleton loader indicates progress.

## Multi-environment behavior

The explorer always reflects the **active** environment from `connectionStore.activeEnvironment`. When you switch envs:

1. The TanStack Query cache for the explorer is **kept** (not purged) — fast switching back
2. A fresh fetch is fired for the new env
3. The explorer shows the previous env's data (slightly faded) until the new fetch lands
4. A small env badge in the explorer header shows which env you're looking at

This makes "compare dev to prod" workflows fast — flip between envs and the structure is right there, even before the new data lands.
