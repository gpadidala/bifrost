# LLM Setup — Claude & OpenAI

Bifröst's chat UI works with **Anthropic Claude** and **OpenAI** out of the box. No proxy, no backend rewrite — the browser talks directly to the LLM provider with your API key, and the LLM is given the live MCP tool catalog.

This page walks through getting a key, picking a model, and tuning the system prompt for Grafana work.

## Anthropic (Claude)

### Getting an API key

1. Go to <https://console.anthropic.com>
2. Sign up or sign in
3. **Settings → API Keys → Create Key**
4. Copy the `sk-ant-...` value (shown once)

### Picking a model

Bifröst's UI exposes the current Claude family in the LLM drawer. Recommendations:

| Model | Best for | Cost |
|---|---|---|
| **`claude-opus-4-6` (1M ctx)** | Complex multi-step Grafana investigations, ad-hoc dashboards-as-code authoring | $$$ |
| **`claude-sonnet-4-6` (1M ctx)** | The default — fast, smart, handles 90% of Grafana Q&A | $$ |
| **`claude-haiku-4-5`** | Cheap one-off tool calls, simple "list X" queries | $ |

For first-time setup, **`claude-sonnet-4-6`** is the right pick. Switch up to opus when you need it.

### Configuring in the UI

1. Open the LLM drawer (gear icon in the header)
2. Provider: **Anthropic**
3. Model: pick from the dropdown
4. API Key: paste the `sk-ant-...` value
5. System prompt: leave the default (see [System prompt](#system-prompt) below)
6. Max tokens: `4096` is a safe default
7. Temperature: `0` for deterministic answers, `0.3` for slightly more variety

The key is stored in `localStorage` (encrypted with your passphrase if set) and is sent **directly from the browser to `api.anthropic.com`**. Bifröst's MCP server never sees the key — there is no proxy.

### Anthropic tool use

Claude's `tools` API is where the MCP magic happens. Bifröst:

1. Pulls the live tool catalog from the MCP server via `tools/list`
2. Translates each tool's Pydantic input schema to Anthropic's `tools` format
3. Includes the tool list in every request
4. Watches the streaming response for `tool_use` blocks
5. Fires the corresponding MCP `tools/call`
6. Feeds the result back as a `tool_result` and continues the stream

This is identical to how Claude Code, the MCP-spec reference implementation, handles tool use — Bifröst is just a different MCP server.

## OpenAI (GPT)

### Getting an API key

1. Go to <https://platform.openai.com>
2. Sign in
3. **Profile → API Keys → Create new secret key**
4. Copy the `sk-proj-...` value

### Picking a model

| Model | Best for | Cost |
|---|---|---|
| **`gpt-4o`** | Complex Grafana investigations | $$ |
| **`gpt-4o-mini`** | Cheap default — handles most Q&A | $ |
| **`o3`** | Reasoning-heavy multi-step queries | $$$ |
| **`o4-mini`** | Cheaper reasoning model | $$ |

For first-time setup, **`gpt-4o-mini`** is the right pick. It's cheap and handles tool calls well.

### OpenAI function calling

OpenAI's `tools` API works the same way as Anthropic's:

1. Bifröst translates MCP tool schemas to OpenAI's `function` format
2. The model emits `tool_calls` in the streaming response
3. Bifröst fires the matching MCP call
4. Result is fed back as a `tool` role message
5. Stream continues

Same loop, slightly different wire format. The chat code abstracts both behind a single `llmClient.stream()` interface in `packages/ui/src/lib/llm-client.ts`.

## System prompt

The default system prompt is tuned for Grafana Q&A. The full text:

```
You are a Grafana assistant powered by Bifröst, a typed MCP gateway to Grafana.

You are connected to:
  • Environment: {{environment}}
  • Role: {{role}}
  • Grafana version: {{grafana_version}}

You have access to ~20 typed tools for reading and (where role permits) modifying
this Grafana instance. Each tool has a Pydantic-typed input schema and a
Pydantic-typed output. The tool catalog is in your tool list.

GUIDELINES:

1. PREFER READS OVER WRITES. If a user's request is ambiguous, default to
   read-only tools and ask before calling write tools.

2. NEVER INVENT IDS. Always discover UIDs by listing or searching first.
   `get_dashboard("api-health")` will fail — use `list_dashboards()` or
   `search_dashboards("api health")` to find the real UID.

3. RESPECT THE ROLE. If a tool returns PermissionError, the user's active role
   is too low. Tell them which role they need and offer to wait while they
   switch — DO NOT retry blindly.

4. SUMMARIZE BIG RESPONSES. `list_dashboards` against a large Grafana can return
   hundreds of entries. Pick out the relevant ones and summarize; don't dump
   raw JSON.

5. INCLUDE GRAFANA DEEP LINKS. When you reference a dashboard, alert, or panel,
   include its URL so the user can click through. The MCP tool responses
   include URLs.

6. ON ERRORS, RUN HEALTH_CHECK. If a tool call fails unexpectedly, call
   `health_check` first to verify Grafana is reachable before trying anything
   else.

7. PARALLELIZE WHEN POSSIBLE. If you need to inspect 12 dashboards, fire 12
   `get_dashboard` calls in parallel — Bifröst's rate limit will protect
   Grafana.

You are concise, technical, and honest about what you don't know.
```

The `{{environment}}`, `{{role}}`, and `{{grafana_version}}` placeholders are interpolated by the UI before each request, so the LLM always knows what it's pointing at.

### Customizing the system prompt

You can edit the prompt in the LLM drawer. Common customizations:

- **Stricter read-only mode** — add: *"Refuse to call any tool that modifies state, even if the user asks. Tell them to switch to a different chat session for write operations."*
- **Org-specific dashboard naming** — add: *"This Grafana uses the naming convention `<service>-<env>-<resource>`. Use this when searching."*
- **Preferred query language** — add: *"For service metrics, prefer LogQL over PromQL because we ship logs more reliably than metrics."*
- **Mandatory deep links** — add: *"Every reference to a dashboard MUST include its grafana.company.com URL."*

Don't make the prompt too long — past ~500 tokens of system prompt, models start ignoring later instructions. Lead with the most important rules.

## Cost & rate limits

The chat panel shows tokens used and estimated cost in the bottom strip. Rough numbers per turn:

| Model | Tokens/turn (avg) | Cost/turn (avg) |
|---|---|---|
| `claude-haiku-4-5` | 2,500 | $0.001 |
| `claude-sonnet-4-6` | 3,000 | $0.012 |
| `claude-opus-4-6` | 3,500 | $0.060 |
| `gpt-4o-mini` | 2,500 | $0.001 |
| `gpt-4o` | 3,000 | $0.020 |

These are dominated by the **MCP tool catalog** in the system prompt — every turn includes the full ~20-tool schema, which is ~1,500 tokens. If you want to cut cost, you can configure the UI to omit tools you don't use (LLM Settings → Tool filter), but the default is "everything available."

Provider rate limits apply normally. If you hit them:

- **Anthropic** — bump your tier in the console; tier 1 is limited
- **OpenAI** — same; you may need to add a payment method to lift the free-tier cap

## Privacy notes

- API keys are stored in `localStorage`, not on Bifröst's server
- API keys are sent **directly from the browser** to Anthropic/OpenAI — Bifröst is not in the path
- Tool call params and results **are** sent to the LLM provider as part of the conversation. If your Grafana data is sensitive (PII, credentials, etc.), this is a real consideration. Most teams use `viewer`-role Bifröst for AI chat to limit what can be exfiltrated, and avoid running queries that return raw PII

## Switching providers mid-conversation

You can change provider/model in the LLM drawer at any time. The conversation history is preserved (it's just a list of messages). The next turn uses the new provider with the same context. This is useful for "I started with `gpt-4o-mini` but it's not getting the answer right — let me try `claude-opus-4-6`."

Note that each provider has a slightly different `tool_use` flavor, so the next turn's tool calls may be formatted differently in the chat UI. The substance is the same.

## Related

- [AI Chat feature](../features/ai-chat.md)
- [MCP Tool Catalog](../features/mcp-tools.md)
- [`packages/ui` reference](../packages/ui.md)
