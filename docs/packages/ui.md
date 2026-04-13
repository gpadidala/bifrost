# `packages/ui` — React Chat UI

`packages/ui` is the browser app: a polished developer-tool UI that wires Claude or GPT to a live Bifröst MCP server. It feels like a power tool, not a consumer app — dark-first, information-dense, technically precise.

## Tech stack

- **React 19** + **TypeScript 5.5** + **Vite 6**
- **Tailwind CSS v4** — no PostCSS config, the new compiler
- **Zustand** — global state (connection config, chat history)
- **TanStack Query v5** — server state (Grafana health, dashboards)
- **Radix UI** primitives — accessible components, no unstyled wrappers
- **`@anthropic-ai/sdk`** + **`openai`** — direct browser → LLM calls, no proxy
- **`react-markdown`** + **`rehype-highlight`** — Markdown rendering for LLM responses
- **`eventsource-parser`** — robust SSE parsing for both LLM streaming *and* MCP

## Layout

```
packages/ui/
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── index.html
├── public/
│   └── bifrost-favicon.svg
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── app/
    │   ├── layout/
    │   │   ├── Shell.tsx           # Sidebar + header + content slot
    │   │   ├── Sidebar.tsx
    │   │   └── Header.tsx          # Env switcher, role badge, LLM gear
    │   ├── connection/
    │   │   ├── ConnectionPage.tsx
    │   │   ├── EnvironmentCard.tsx # one card per env
    │   │   ├── RoleSelector.tsx    # segmented control
    │   │   └── TransportConfig.tsx
    │   ├── chat/
    │   │   ├── ChatPage.tsx
    │   │   ├── MessageList.tsx
    │   │   ├── Message.tsx         # markdown + tool-call cards
    │   │   ├── ToolCallCard.tsx    # collapsible tool name + params + result
    │   │   ├── ChatInput.tsx
    │   │   └── ConversationList.tsx
    │   └── explorer/
    │       ├── ExplorerPanel.tsx
    │       ├── FolderTree.tsx
    │       ├── DatasourcesList.tsx
    │       └── AlertsList.tsx
    ├── stores/
    │   ├── connectionStore.ts      # Zustand: env configs, active env/role
    │   └── chatStore.ts            # Zustand: messages, active LLM, history
    ├── hooks/
    │   ├── useGrafanaHealth.ts     # TanStack Query: per-env health polling
    │   ├── useMCPClient.ts         # SSE client + tool catalog
    │   └── useLLMStream.ts         # Streaming LLM call w/ tool_use
    ├── lib/
    │   ├── mcp-client.ts           # MCP SSE client
    │   ├── llm-client.ts           # OpenAI + Anthropic unified interface
    │   ├── crypto.ts               # Web Crypto helpers for localStorage encryption
    │   └── env-export.ts           # Export connection config as .env
    ├── components/ui/              # Radix-based primitives
    │   ├── Button.tsx
    │   ├── Card.tsx
    │   ├── Input.tsx
    │   ├── SegmentedControl.tsx
    │   ├── Drawer.tsx
    │   ├── Tooltip.tsx
    │   └── Badge.tsx
    └── styles/
        └── tailwind.css            # @import "tailwindcss"; + theme tokens
```

## State model

Two Zustand stores. That's it.

### `connectionStore`

```typescript
interface ConnectionState {
  environments: Record<EnvName, EnvironmentConfig>
  activeEnvironment: EnvName
  activeRole: GrafanaRole
  transport: { mode: "sse" | "http"; host: string; port: number; pathPrefix: string }
  passphrase: string | null   // for localStorage encryption

  setActiveEnvironment: (env: EnvName) => void
  setActiveRole: (role: GrafanaRole) => void
  updateEnvironment: (env: EnvName, patch: Partial<EnvironmentConfig>) => void
  testConnection: (env: EnvName, role: GrafanaRole) => Promise<HealthStatus>
  exportEnv: () => string
  importEnv: (text: string) => void
}
```

Persisted to `localStorage` via `zustand/middleware/persist`. If `passphrase` is set, the persist serializer encrypts the blob with AES-GCM via Web Crypto API before writing.

### `chatStore`

```typescript
interface ChatState {
  conversations: Record<string, Conversation>
  activeConversationId: string

  llm: {
    provider: "anthropic" | "openai"
    model: string
    apiKey: string
    systemPrompt: string
    maxTokens: number
    temperature: number
  }

  newConversation: () => string
  addMessage: (id: string, msg: Message) => void
  updateMessage: (id: string, msgId: string, patch: Partial<Message>) => void
  setLLM: (patch: Partial<ChatState["llm"]>) => void
}
```

Also persisted to `localStorage`. The `apiKey` field is only ever read from this store and sent directly to Anthropic/OpenAI — Bifröst's MCP server never sees it.

## The chat loop

```
┌─────────┐  user message
│  User   │ ──────────────────────┐
└─────────┘                       ▼
                            ┌──────────┐
                            │ chatStore│  add user message
                            └─────┬────┘
                                  │
                                  ▼
                          ┌────────────────┐
                          │ useLLMStream() │
                          └───┬────────┬───┘
                              │        │
              system prompt   │        │ tool catalog (from MCP)
              + history       │        │
                              ▼        ▼
                  ┌──────────────────────────────┐
                  │   Anthropic / OpenAI API     │
                  │   (browser → LLM provider)   │
                  └──────────┬───────────────────┘
                             │  tool_use detected
                             ▼
                  ┌──────────────────────────────┐
                  │  useMCPClient().callTool()   │
                  │  → MCP server over SSE       │
                  └──────────┬───────────────────┘
                             │  tool_result
                             ▼
              feed result back into the LLM stream
                             │
                             ▼
                  final assistant message rendered
```

The loop is implemented in `hooks/useLLMStream.ts`:

```typescript
async function streamConversation(messages: Message[]) {
  const tools = await mcpClient.listTools()         // pulled once and cached

  const stream = llmClient.stream({
    model, messages, tools, system: systemPrompt
  })

  for await (const event of stream) {
    if (event.type === "text_delta") {
      chatStore.appendDelta(event.delta)
    }
    if (event.type === "tool_use") {
      chatStore.addToolCall(event.name, event.input)
      const result = await mcpClient.callTool(event.name, event.input)
      chatStore.addToolResult(event.id, result)
      // continue the loop with tool_result fed back to the LLM
      messages.push({ role: "user", content: [{ type: "tool_result", tool_use_id: event.id, content: result }] })
      return streamConversation(messages)
    }
  }
}
```

The recursion handles multi-turn tool calls cleanly — the LLM can call one tool, see the result, decide it needs another, and so on, with the UI rendering tool-call cards as each one fires.

## Connection config UI

Three environment cards in a vertical stack. Each card shows:

- **Grafana URL** input (validated with `useGrafanaHealth` debounced ping)
- **Three service-account token inputs** — viewer / editor / admin, type=password
- **Per-role connection status badges** — green ✓, red ✗, gray —
- **Test Connection** button → calls `/healthz` with each token
- **Active env radio** — pick which env is "selected"
- **Active role segmented control** — pick which token is in use

All edits are saved to `connectionStore` and persisted on change. There's an **Export** button that writes the current config as a downloadable `.env` file (see [Export/Import](#exportimport-as-env)).

## LLM config drawer

A Radix `Dialog` triggered by the gear icon in the header. Lets the user configure:

- **Provider** — Anthropic or OpenAI radio
- **Model** picker — different list per provider:
  - Anthropic: `claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4`
  - OpenAI: `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini`
- **API key** — password input
- **System prompt** — textarea, 8 rows, defaults to a Grafana-aware prompt
- **Max tokens** — number input
- **Temperature** — slider, 0 to 1

All fields are fed to the LLM client's `stream()` call. There's no "save" button — fields write back to `chatStore.llm` on blur.

## Resource explorer

Left-side collapsible panel, three sections:

1. **Folders** — tree of folders → dashboards → panels. Lazy-loaded: clicking a folder fires `list_dashboards(folder_uid=...)`, clicking a dashboard fires `get_dashboard_panels(uid=...)`.
2. **Datasources** — flat list with type badges (Prometheus, Loki, Mimir, Tempo, ...).
3. **Alert rules** — grouped by folder, with state badges (firing/normal/pending/no_data).

Clicking any item adds a **context card** to the chat input — "Ask AI about this dashboard" — which prepends a structured reference to the user's next message:

```
[Context: dashboard "Prod API Health" (uid=abc123, 12 panels, prometheus + loki)]
What's the most expensive panel here?
```

The LLM can then call `get_dashboard` with the UID and answer in one round trip.

## Theme

Defined in `tailwind.config.ts` and `styles/tailwind.css`:

```css
@theme {
  --color-bg-base:        #0d0d12;
  --color-bg-surface:     #14141c;
  --color-bg-elevated:    #1c1c28;
  --color-border-subtle:  #2a2a3a;

  --color-accent:         #f59e0b;   /* electric amber */
  --color-success:        #22c55e;   /* connected */
  --color-error:          #ef4444;   /* errors */

  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
  --font-sans: 'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif;
}
```

Code, tokens, URLs, and timestamps render in JetBrains Mono. UI copy renders in IBM Plex Sans. The accent color (amber) is used for active states only — never for decoration.

## Build & dev

```bash
pnpm --filter ./packages/ui dev      # vite dev server on :5173
pnpm --filter ./packages/ui build    # production build to packages/ui/dist
pnpm --filter ./packages/ui preview  # serve the built app locally
pnpm --filter ./packages/ui test     # vitest unit tests
pnpm --filter ./packages/ui lint     # eslint
pnpm --filter ./packages/ui typecheck # tsc --noEmit
```

The production build is a static SPA — drop `dist/` behind any web server. The Docker image uses nginx-alpine.

## Export/Import as `.env`

The Connection Config page has an **Export** button that serializes the current `connectionStore` to a `.env` blob with the same format as `.env.example`:

```env
GRAFANA_MCP_ACTIVE_ENVIRONMENT=dev
GRAFANA_MCP_ACTIVE_ROLE=viewer
GRAFANA_MCP_ENVIRONMENTS__DEV__BASE_URL=http://localhost:3000
GRAFANA_MCP_ENVIRONMENTS__DEV__SERVICE_ACCOUNTS__VIEWER=glsa_xxx
...
```

The user gets a `bifrost.env` file they can drop next to a server install. The **Import** button does the reverse — paste a `.env` blob and the store reconstructs from it.

This is the path of least resistance for "I configured it in the UI and now I want to run the server in Docker."
