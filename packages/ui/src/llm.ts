// Unified streaming LLM client — Anthropic + OpenAI — with MCP tool-use loop.
//
// Both providers support browser-side calls. Keys live in localStorage,
// never touch the Bifröst backend. Tool calls are routed through the
// Bifröst REST bridge (/api/tools/call) so role enforcement, pooling,
// and retry all keep working.

import type { BifrostClient } from "./api";
import type { LLMConfig } from "./store";

export interface MCPToolDef {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  min_role: "viewer" | "editor" | "admin";
}

export type LLMEvent =
  | { type: "text"; delta: string }
  | { type: "tool_start"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; id: string; result: unknown; error?: string; durationMs: number }
  | { type: "done" }
  | { type: "error"; message: string };

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  // internal: for the multi-turn loop we keep the "blocks" representation too
}

export interface StreamRequest {
  config: LLMConfig;
  tools: MCPToolDef[];
  messages: ChatTurn[];
  bridge: BifrostClient;
  onEvent: (event: LLMEvent) => void;
  signal?: AbortSignal;
}

// Fetch the tool catalog from the Bifröst bridge
export async function fetchToolCatalog(bridge: BifrostClient): Promise<MCPToolDef[]> {
  const r = await fetch(`${bridge.baseUrl}/api/tools`);
  const env = (await r.json()) as { ok: true; data: MCPToolDef[] } | { ok: false; error: string; message: string };
  if (!env.ok) throw new Error(`${env.error}: ${env.message}`);
  return env.data;
}

// Invoke a single tool through the Bifröst bridge
async function callTool(
  bridge: BifrostClient,
  name: string,
  args: Record<string, unknown>,
): Promise<{ result: unknown; error?: string; durationMs: number }> {
  const t0 = performance.now();
  try {
    const r = await fetch(`${bridge.baseUrl}/api/tools/call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, arguments: args }),
    });
    const env = (await r.json()) as
      | { ok: true; data: unknown }
      | { ok: false; error: string; message: string };
    const durationMs = Math.round(performance.now() - t0);
    if (!env.ok) return { result: null, error: `${env.error}: ${env.message}`, durationMs };
    return { result: env.data, durationMs };
  } catch (err) {
    const durationMs = Math.round(performance.now() - t0);
    return { result: null, error: err instanceof Error ? err.message : String(err), durationMs };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Public entry point
// ─────────────────────────────────────────────────────────────────────────────

export async function runChat(req: StreamRequest): Promise<void> {
  if (req.config.provider === "anthropic") {
    return runAnthropic(req);
  }
  return runOpenAI(req);
}

// ─────────────────────────────────────────────────────────────────────────────
// Anthropic — messages API with tool_use, SSE streaming
// ─────────────────────────────────────────────────────────────────────────────

interface AnthropicContentBlock {
  type: "text" | "tool_use" | "tool_result";
  text?: string;
  id?: string;
  name?: string;
  input?: Record<string, unknown>;
  tool_use_id?: string;
  content?: string;
  is_error?: boolean;
}

interface AnthropicMessage {
  role: "user" | "assistant";
  content: string | AnthropicContentBlock[];
}

async function runAnthropic(req: StreamRequest): Promise<void> {
  const { config, tools, messages, bridge, onEvent, signal } = req;

  const anthropicMessages: AnthropicMessage[] = messages.map((m) => ({
    role: m.role,
    content: m.content,
  }));

  const anthropicTools = tools.map((t) => ({
    name: t.name,
    description: t.description,
    input_schema: normalizeAnthropicSchema(t.input_schema),
  }));

  // Tool loop: keep calling until the model stops emitting tool_use blocks
  for (let iter = 0; iter < 8; iter++) {
    if (signal?.aborted) return;

    const body = {
      model: config.model,
      max_tokens: config.maxTokens,
      temperature: config.temperature,
      system: config.systemPrompt,
      tools: anthropicTools,
      messages: anthropicMessages,
      stream: true,
    };

    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": config.apiKey,
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!r.ok || !r.body) {
      const text = await r.text();
      onEvent({ type: "error", message: `anthropic ${r.status}: ${text.slice(0, 400)}` });
      return;
    }

    // Parse the SSE stream and accumulate assistant blocks
    const assistantBlocks: AnthropicContentBlock[] = [];
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentToolInputJson = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by \n\n
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = frame
          .split("\n")
          .find((l) => l.startsWith("data: "));
        if (!dataLine) continue;
        const jsonStr = dataLine.slice(6);
        if (jsonStr === "[DONE]") continue;
        let evt: any;
        try {
          evt = JSON.parse(jsonStr);
        } catch {
          continue;
        }

        if (evt.type === "content_block_start") {
          if (evt.content_block?.type === "text") {
            assistantBlocks[evt.index] = { type: "text", text: "" };
          } else if (evt.content_block?.type === "tool_use") {
            assistantBlocks[evt.index] = {
              type: "tool_use",
              id: evt.content_block.id,
              name: evt.content_block.name,
              input: {},
            };
            currentToolInputJson = "";
          }
        } else if (evt.type === "content_block_delta") {
          const block = assistantBlocks[evt.index];
          if (!block) continue;
          if (evt.delta?.type === "text_delta" && block.type === "text") {
            block.text = (block.text ?? "") + evt.delta.text;
            onEvent({ type: "text", delta: evt.delta.text });
          } else if (evt.delta?.type === "input_json_delta" && block.type === "tool_use") {
            currentToolInputJson += evt.delta.partial_json ?? "";
          }
        } else if (evt.type === "content_block_stop") {
          const block = assistantBlocks[evt.index];
          if (block?.type === "tool_use") {
            try {
              block.input = currentToolInputJson ? JSON.parse(currentToolInputJson) : {};
            } catch {
              block.input = {};
            }
            currentToolInputJson = "";
          }
        } else if (evt.type === "message_stop") {
          // Stream ends — we'll fall through to process tool_use blocks
        }
      }
    }

    // Append the assistant turn to the conversation
    const cleanBlocks = assistantBlocks.filter((b): b is AnthropicContentBlock => !!b);
    anthropicMessages.push({ role: "assistant", content: cleanBlocks });

    // Are there any tool_use blocks? If not, we're done.
    const toolUses = cleanBlocks.filter((b) => b.type === "tool_use");
    if (toolUses.length === 0) {
      onEvent({ type: "done" });
      return;
    }

    // Execute each tool through the Bifröst bridge and build a tool_result turn
    const toolResultBlocks: AnthropicContentBlock[] = [];
    for (const tu of toolUses) {
      if (signal?.aborted) return;
      onEvent({ type: "tool_start", id: tu.id!, name: tu.name!, input: tu.input ?? {} });
      const { result, error, durationMs } = await callTool(bridge, tu.name!, tu.input ?? {});
      onEvent({ type: "tool_result", id: tu.id!, result, error, durationMs });
      toolResultBlocks.push({
        type: "tool_result",
        tool_use_id: tu.id!,
        content: error ? error : JSON.stringify(result).slice(0, 20000),
        is_error: !!error,
      });
    }
    anthropicMessages.push({ role: "user", content: toolResultBlocks });
  }

  onEvent({ type: "error", message: "tool loop exceeded 8 iterations" });
}

function normalizeAnthropicSchema(schema: Record<string, unknown>): Record<string, unknown> {
  // Anthropic requires input_schema to have `type: "object"` and a `properties` map
  const base = { type: "object", properties: {}, ...schema };
  if (!(base as any).properties) (base as any).properties = {};
  return base;
}

// ─────────────────────────────────────────────────────────────────────────────
// OpenAI — chat completions API with tools, SSE streaming
// ─────────────────────────────────────────────────────────────────────────────

interface OpenAIMessage {
  role: "system" | "user" | "assistant" | "tool";
  content?: string | null;
  tool_calls?: Array<{
    id: string;
    type: "function";
    function: { name: string; arguments: string };
  }>;
  tool_call_id?: string;
  name?: string;
}

async function runOpenAI(req: StreamRequest): Promise<void> {
  const { config, tools, messages, bridge, onEvent, signal } = req;

  const oaMessages: OpenAIMessage[] = [
    { role: "system", content: config.systemPrompt },
    ...messages.map((m) => ({ role: m.role, content: m.content } as OpenAIMessage)),
  ];

  const oaTools = tools.map((t) => ({
    type: "function" as const,
    function: {
      name: t.name,
      description: t.description,
      parameters: normalizeOpenAISchema(t.input_schema),
    },
  }));

  for (let iter = 0; iter < 8; iter++) {
    if (signal?.aborted) return;

    const body = {
      model: config.model,
      messages: oaMessages,
      tools: oaTools,
      tool_choice: "auto" as const,
      max_tokens: config.maxTokens,
      temperature: config.temperature,
      stream: true,
    };

    const r = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${config.apiKey}`,
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!r.ok || !r.body) {
      const text = await r.text();
      onEvent({ type: "error", message: `openai ${r.status}: ${text.slice(0, 400)}` });
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    let assistantContent = "";
    const partialToolCalls: Record<number, { id: string; name: string; argsJson: string }> = {};

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, sep).trim();
        buffer = buffer.slice(sep + 1);
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6);
        if (jsonStr === "[DONE]") continue;
        let evt: any;
        try {
          evt = JSON.parse(jsonStr);
        } catch {
          continue;
        }
        const delta = evt.choices?.[0]?.delta;
        if (!delta) continue;
        if (typeof delta.content === "string") {
          assistantContent += delta.content;
          onEvent({ type: "text", delta: delta.content });
        }
        if (Array.isArray(delta.tool_calls)) {
          for (const tcd of delta.tool_calls) {
            const idx = tcd.index ?? 0;
            if (!partialToolCalls[idx]) {
              partialToolCalls[idx] = {
                id: tcd.id ?? `call_${idx}`,
                name: "",
                argsJson: "",
              };
            }
            const pc = partialToolCalls[idx];
            if (tcd.id) pc.id = tcd.id;
            if (tcd.function?.name) pc.name = tcd.function.name;
            if (tcd.function?.arguments) pc.argsJson += tcd.function.arguments;
          }
        }
      }
    }

    const toolCallsList = Object.values(partialToolCalls);

    if (toolCallsList.length === 0) {
      oaMessages.push({ role: "assistant", content: assistantContent });
      onEvent({ type: "done" });
      return;
    }

    // Append the assistant turn (may contain both content and tool_calls)
    oaMessages.push({
      role: "assistant",
      content: assistantContent || null,
      tool_calls: toolCallsList.map((tc) => ({
        id: tc.id,
        type: "function",
        function: { name: tc.name, arguments: tc.argsJson || "{}" },
      })),
    });

    for (const tc of toolCallsList) {
      if (signal?.aborted) return;
      let args: Record<string, unknown> = {};
      try {
        args = tc.argsJson ? JSON.parse(tc.argsJson) : {};
      } catch {
        args = {};
      }
      onEvent({ type: "tool_start", id: tc.id, name: tc.name, input: args });
      const { result, error, durationMs } = await callTool(bridge, tc.name, args);
      onEvent({ type: "tool_result", id: tc.id, result, error, durationMs });
      oaMessages.push({
        role: "tool",
        tool_call_id: tc.id,
        content: error ? error : JSON.stringify(result).slice(0, 20000),
      });
    }
  }

  onEvent({ type: "error", message: "tool loop exceeded 8 iterations" });
}

function normalizeOpenAISchema(schema: Record<string, unknown>): Record<string, unknown> {
  const base: Record<string, unknown> = { type: "object", properties: {}, ...schema };
  if (!(base as any).properties) (base as any).properties = {};
  return base;
}
