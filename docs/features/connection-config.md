# Connection Config Panel

The Connection Config page is the first thing every user sees on first run. It's where you wire Bifröst to your Grafana environments, set the active env + role, and (if you want) export everything as a `.env` file for the server side.

## Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Connection                                            ⚙ LLM Drawer │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  ● dev               (Active)                       ✓ Connected│  │
│  │  ─────────────────────────────────────────────────────────────│  │
│  │  Grafana URL                                                  │  │
│  │  ┌───────────────────────────────────────────────────────────┐│  │
│  │  │ http://localhost:3000                                     ││  │
│  │  └───────────────────────────────────────────────────────────┘│  │
│  │                                                               │  │
│  │  Service Account Tokens                                       │  │
│  │  Viewer  ●●●●●●●●●●●●●●●●●●●●  ✓                              │  │
│  │  Editor  ●●●●●●●●●●●●●●●●●●●●  ✓                              │  │
│  │  Admin   ●●●●●●●●●●●●●●●●●●●●  ✓                              │  │
│  │                                                               │  │
│  │  TLS Verify  [ off ]   Timeout  [ 30 ]   Rate Limit  [ 20 ]   │  │
│  │                                                               │  │
│  │  [ Test Connection ]                          [ Set Active ]  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  ○ perf                                          ⚠ Untested   │  │
│  │  ...                                                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  ○ prod                                          ✗ 401 Editor │  │
│  │  ...                                                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Active Role:  [ Viewer | Editor | Admin ]                          │
│                                                                     │
│  ┌── Transport ──────────────────────────────────────────────────┐  │
│  │  Mode  ○ SSE  ● HTTP                                          │  │
│  │  Host  [ 0.0.0.0 ]      Port  [ 8765 ]   Path  [ /mcp ]       │  │
│  │  MCP URL preview:  http://0.0.0.0:8765/mcp/sse  (read-only)   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  [ Export .env ]    [ Import .env ]    [ Set Encryption Passphrase ]│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Environment cards

One card per environment, always in `dev` → `perf` → `prod` order. Each card has:

### Header

- **Radio dot** (`●` / `○`) showing whether this env is the **active** one
- **Name** in JetBrains Mono
- **Connection status badge** — green ✓ Connected, red ✗ {error}, gray ⚠ Untested

### Grafana URL

A single input. Validated as you type:

- Must be a valid URL
- Trailing slash auto-stripped
- Live-pinged on blur (debounced 500ms) — turns green if Grafana responds, red if not
- The ping uses a HEAD request to `/api/health` and does **not** consume your tokens

### Three token inputs

`Viewer`, `Editor`, `Admin` — each is a `type=password` input with a status badge to its right. The badge meanings:

| Badge | Meaning |
|---|---|
| ✓ green | Token works (validated against this env's `/api/health` with `Authorization: Bearer ...`) |
| ✗ red | Token returned 401 / 403 |
| — gray | Token is empty or untested |

The validation runs when you click **Test Connection** at the bottom of the card. It does not run automatically as you type because token rotations are common and we don't want to hammer Grafana on every keystroke.

### Per-env settings

- **TLS Verify** — toggle. Off only for self-signed dev clusters.
- **Timeout** — seconds. Per-request HTTP timeout. Default 30.
- **Rate Limit** — RPS. Max in-flight requests per second across all roles. Default 10 for prod, 20 for dev.

These map directly to the [Pydantic model fields](../architecture/environments.md#the-pydantic-model).

### Card actions

- **Test Connection** — pings Grafana with all three tokens and updates the badges
- **Set Active** — promotes this env to the active environment

## Active role selector

A segmented control underneath the env cards:

```
[ Viewer | Editor | Admin ]
```

Picks the active role for the active env. Updates `connectionStore.activeRole` and re-issues the MCP `initialize` handshake. The role badge in the header (`VIEWER` / `EDITOR` / `ADMIN`) updates immediately.

## Transport config

A small section at the bottom of the page:

- **Mode** — SSE or HTTP radio
- **Host** + **Port** + **Path Prefix** inputs
- **MCP server URL preview** — a read-only field showing the computed URL based on the above

This section configures the URL the **UI** uses to connect to the **MCP server**. It does not configure how the MCP server itself binds — that's done via `--host` and `--port` flags on `grafana-mcp serve` (or env vars). The UI's role here is "where do I send my SSE / HTTP calls."

## Export / Import as `.env`

The two big buttons at the bottom:

### Export .env

Serializes the current connection config to a `.env` blob in the same format as `.env.example` and triggers a browser download. The file is named `bifrost-{timestamp}.env`.

This is the fast path for "I configured Bifröst in the UI, now I want to run the server in Docker." Drop the file next to `docker-compose.yml`, rename to `.env`, `docker compose up`, done.

### Import .env

Opens a textarea modal. Paste a `.env` blob, click **Import**, and the store reconstructs from it. Existing config is **replaced** (with a confirmation dialog).

The parser handles:

- Comments (`#`)
- Empty lines
- Quoted values (`"glsa xxx"`, `'glsa xxx'`)
- The full nested `__` delimiter syntax

It does **not** handle env-var interpolation (`${PROD_VIEWER_TOKEN}`) — those are passed through verbatim. The UI doesn't have a parent process to interpolate against.

## Encrypted localStorage

By default the connection config is stored in `localStorage` as plain JSON. This is fine for personal dev machines but uncomfortable for shared workstations. Click **Set Encryption Passphrase** to enable Web Crypto encryption:

1. Pop-up asks for a passphrase (twice)
2. Passphrase is run through PBKDF2 (100k iterations, SHA-256)
3. Derived key is held in memory only — never stored
4. The Zustand persist serializer encrypts the blob with AES-GCM before writing
5. On page load, the store asks for the passphrase before unlocking

If you forget the passphrase, the only path is to clear `localStorage` and re-enter your config. There's no recovery — that's the point.

## Health polling

When the page is open, `useGrafanaHealth` (TanStack Query) polls each connected environment every 30 seconds:

```typescript
useQuery({
  queryKey: ["health", env, role],
  queryFn: () => mcpClient.callTool("health_check", { environment: env, role }),
  refetchInterval: 30_000,
  enabled: hasToken(env, role),
})
```

If a token starts returning 401 (rotated upstream), the badge flips to red within 30 seconds. The user knows immediately, not when their next chat call fails.

## What's *not* in this panel

- **LLM config** — that's the gear-icon drawer, see [AI Chat](ai-chat.md)
- **System prompt editing** — same drawer
- **Conversation history** — the chat sidebar
- **Tool catalog** — the resource explorer + the chat tool-call cards

The Connection Config page is intentionally narrow: connections in, nothing else.
