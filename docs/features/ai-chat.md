# AI Chat Interface

The chat panel is the headline feature of `packages/ui`. It wires Claude or GPT to the live MCP server so that natural-language questions translate into typed Grafana tool calls — and the LLM gets to see the typed responses and turn them back into prose.

This page documents the user-facing feature. For the React + state internals, see [`packages/ui`](../packages/ui.md).

## The big idea

```
User: "Which dashboards depend on the prometheus-prod datasource?"
   │
   ▼
LLM (Claude/GPT) — sees the user message + the MCP tool catalog
   │
   ▼
LLM picks: list_dashboards()  → tool_use
   │
   ▼
MCP SSE client → Bifröst → Grafana → typed list[DashboardSummary]
   │
   ▼
LLM picks: get_dashboard(uid="abc") for each → tool_use (parallel)
   │
   ▼
LLM filters by datasource UID, summarizes:
   │
   ▼
"7 dashboards reference prometheus-prod: API Health, …"
```

The user typed one sentence. The LLM made ~8 tool calls. The user sees one summary plus 8 collapsible tool-call cards they can expand if they want to verify.

## Anatomy of a chat turn

```
┌──────────────────────────────────────────────────────────┐
│  ┌─ user ─────────────────────────────────────────────┐  │
│  │ Which dashboards depend on prometheus-prod?        │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ assistant (streaming) ────────────────────────────┐  │
│  │ I'll check by listing dashboards and looking at    │  │
│  │ each one's datasource references...                │  │
│  │                                                    │  │
│  │ ▼ list_dashboards()                                │  │
│  │   ┌──────────────────────────────────────┐         │  │
│  │   │ params: {}                           │         │  │
│  │   │ result: 47 dashboards                │         │  │
│  │   │ duration: 34ms                       │         │  │
│  │   └──────────────────────────────────────┘         │  │
│  │                                                    │  │
│  │ ▶ get_dashboard(uid="api-health")    → 1 ref       │  │
│  │ ▶ get_dashboard(uid="kafka")         → 0 refs      │  │
│  │ ▶ get_dashboard(uid="postgres")      → 1 ref       │  │
│  │ ... (44 more, collapsed by default)                │  │
│  │                                                    │  │
│  │ Found 7 dashboards that reference prometheus-prod: │  │
│  │   1. API Health (3 panels)                         │  │
│  │   2. Postgres Overview (5 panels)                  │  │
│  │   ...                                              │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## Tool-call card

Every tool call gets its own card inside the assistant message. The card has three states:

- **Pending** — the LLM has emitted a `tool_use` block but the MCP call hasn't returned yet. Spinner.
- **Resolved** — the call returned. Card shows `params`, `result`, `duration`. Click to expand/collapse.
- **Errored** — the call raised. Card is red. Shows the error class (e.g. `PermissionError`, `GrafanaError`), the message, and a "retry" button.

The card is collapsible. By default the **first** call in a turn is expanded and the rest are collapsed — most users only care about the summary, not the 47 individual `get_dashboard` calls.

## Streaming

Bifröst's chat uses **two layers of streaming**:

1. **LLM → UI** — the LLM streams text deltas via the provider's SSE/streaming API. Words appear as they're generated.
2. **MCP → UI** — when the LLM emits a `tool_use` block, the UI shows a pending card *immediately*, fires the MCP call, and resolves the card when the response arrives.

This means the user sees the LLM thinking, then sees the tool call fire, then sees the result, then sees the LLM continue thinking with the result in hand. All in real time.

## Conversation history

Conversations are kept in `chatStore` (Zustand) and persisted to `localStorage`. The sidebar lists every conversation with its first user message as the title.

- **New Chat** button — starts a fresh conversation
- **Click** a sidebar entry — loads that conversation into the main pane
- **Right-click → Delete** — drops it from history
- **Right-click → Rename** — set a custom title

There's no server-side history. Closing the browser doesn't lose anything; clearing `localStorage` does.

## System prompt

The default system prompt is tuned for Grafana Q&A and Bifröst's tool surface. It tells the LLM:

- Which environment + role it's connected to (dynamically interpolated each turn)
- What tools are available
- The current Grafana version (from `get_server_info` on session start)
- The recommended pattern for multi-step questions
- Safety guardrails: never invent UIDs, always ping `health_check` if a call fails, prefer read tools over write tools when ambiguous

You can override the prompt in **LLM Settings**. The default is good for first-time users; power users tune it for their org (e.g., "always include the Grafana deep link in your summaries", "prefer LogQL over PromQL for service metrics").

## Per-message context cards

The Resource Explorer (left panel) has a **"Ask AI about this"** action on every dashboard, datasource, and alert rule. Clicking it:

1. Adds a **context card** to the chat input
2. Pre-fills a structured reference like `[Context: dashboard "API Health" (uid=abc, 12 panels)]`
3. Focuses the input so the user can type their question

The LLM gets the context card as part of the user message and can use the UID in its first tool call without having to search for it. This is the fastest path from "I'm looking at a thing" to "tell me about this thing."

## Multi-turn tool loops

Some questions require multiple rounds of tool calls. The chat handles these natively:

```
User:   "Are any datasources in dev not configured in prod?"
LLM:    [tool_use: list_datasources] (env=dev)
        [tool_use: list_datasources] (env=prod)
        Comparing... here are 3 datasources in dev that aren't in prod:
        - tempo-dev (TempO) — only exists in dev
        - mimir-dev (Mimir) — only exists in dev
        - postgres-staging (PostgreSQL) — only exists in dev

User:   "Why is tempo-dev only in dev? Check if it's referenced in any prod dashboards."
LLM:    [tool_use: list_dashboards] (env=prod)
        [tool_use: get_dashboard] x12 (env=prod, parallel)
        No prod dashboards reference tempo-dev. It looks like a dev-only datasource — safe to ignore.
```

The LLM is responsible for the planning. The chat just keeps the loop running until the LLM emits a final `text` block with no `tool_use`.

## Cost & rate-limit awareness

The bottom of the chat panel shows a small status strip:

- **Tokens used** — running total for this conversation (sent + received)
- **Estimated cost** — based on the model's published per-token price
- **MCP rate-limit headroom** — current `asyncio.Semaphore` queue depth on the server

If the user is burning through `claude-opus-4` tokens on a 50-turn conversation, this strip is the early warning. Click it to open a breakdown by message.

## Regenerate, copy, edit

Standard chat affordances on every assistant message:

- **Regenerate** — re-run the same prompt (and re-fire any tool calls). Useful if the LLM picked the wrong tool.
- **Copy** — copies the message body to clipboard, with code blocks intact.
- **Edit** — edit the *previous* user message and re-run from there. Same as ChatGPT's edit affordance.

## Failure modes

What happens when things go wrong:

| Failure | UI behavior |
|---|---|
| LLM API key invalid | Toast error, "Open LLM Settings" button. Chat input disabled until fixed. |
| MCP server unreachable | Tool-call card shows "MCP server offline". Chat continues; LLM is told via a synthetic tool result. |
| Tool returns `PermissionError` | Tool-call card is red, message says "needs role X". LLM relays this to the user and offers to switch the active role. |
| Tool returns `GrafanaError` | Tool-call card is red with the HTTP status. LLM relays the error and usually suggests `health_check`. |
| LLM hits rate limit | Toast error with retry-after. Auto-retries after the delay. |

The principle: **never fail silently, always show the user what went wrong, always give the LLM enough context to recover.**
