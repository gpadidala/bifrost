// Tiny localStorage-backed store for UI preferences:
// - list of known MCP servers (URL + label)
// - currently selected server
// - LLM config (provider, model, key, system prompt)
// - chat conversations
// Plain pattern, no Zustand dependency — keeps the footprint minimal.

import { useEffect, useState } from "react";

export interface MCPServerEntry {
  id: string;
  label: string;
  url: string;
}

export type LLMProvider = "builtin" | "anthropic" | "openai";

export interface LLMConfig {
  provider: LLMProvider;
  model: string;
  apiKey: string;
  systemPrompt: string;
  maxTokens: number;
  temperature: number;
}

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: unknown;
  error?: string;
  durationMs?: number;
  status: "pending" | "ok" | "error";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  createdAt: number;
  streaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

const KEY = "bifrost-ui-v2";

interface Persisted {
  servers: MCPServerEntry[];
  activeServerId: string;
  llm: LLMConfig;
  conversations: Conversation[];
  activeConversationId: string | null;
}

const DEFAULT_SYSTEM_PROMPT =
  "You are a Grafana assistant powered by Bifröst, a typed MCP gateway to Grafana.\n\n" +
  "You have access to typed MCP tools for reading and (where role permits) modifying the connected Grafana instance. " +
  "Every tool has a JSON Schema input and a typed output.\n\n" +
  "Guidelines:\n" +
  "1. PREFER READS OVER WRITES. If a user's request is ambiguous, default to read-only tools.\n" +
  "2. NEVER INVENT IDS. Discover UIDs via list_dashboards or search_dashboards first.\n" +
  "3. RESPECT ROLES. If a tool returns PermissionError, tell the user which role they need — don't retry.\n" +
  "4. SUMMARIZE BIG RESPONSES. Don't dump raw JSON.\n" +
  "5. PARALLELIZE when you need to inspect many resources — Bifröst's rate limit will protect Grafana.\n" +
  "Be concise, technical, and honest about what you don't know.";

const DEFAULTS: Persisted = {
  servers: [{ id: "local", label: "Local (Docker)", url: "http://127.0.0.1:8765" }],
  activeServerId: "local",
  llm: {
    provider: "builtin",
    model: "bifrost-intent-v1",
    apiKey: "",
    systemPrompt: DEFAULT_SYSTEM_PROMPT,
    maxTokens: 4096,
    temperature: 0.2,
  },
  conversations: [],
  activeConversationId: null,
};

function load(): Persisted {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    return {
      ...DEFAULTS,
      ...parsed,
      llm: { ...DEFAULTS.llm, ...(parsed.llm ?? {}) },
      servers: parsed.servers && parsed.servers.length > 0 ? parsed.servers : DEFAULTS.servers,
      conversations: parsed.conversations ?? [],
    };
  } catch {
    return DEFAULTS;
  }
}

function save(p: Persisted): void {
  localStorage.setItem(KEY, JSON.stringify(p));
}

// Reactive singleton — all hook consumers share the same state.
let state: Persisted = load();
const subs = new Set<() => void>();

function emit(): void {
  save(state);
  subs.forEach((fn) => fn());
}

function genId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function usePersistedStore() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((x) => x + 1);
    subs.add(fn);
    return () => {
      subs.delete(fn);
    };
  }, []);

  return {
    // ── MCP servers ─────────────────────────────────────────
    servers: state.servers,
    activeServerId: state.activeServerId,
    activeServer: state.servers.find((s) => s.id === state.activeServerId) ?? state.servers[0]!,
    setActiveServer: (id: string) => {
      state = { ...state, activeServerId: id };
      emit();
    },
    addServer: (label: string, url: string) => {
      const id = genId("srv");
      state = {
        ...state,
        servers: [...state.servers, { id, label, url: url.replace(/\/$/, "") }],
        activeServerId: id,
      };
      emit();
    },
    updateServer: (id: string, patch: Partial<MCPServerEntry>) => {
      state = {
        ...state,
        servers: state.servers.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      };
      emit();
    },
    removeServer: (id: string) => {
      if (state.servers.length <= 1) return;
      const remaining = state.servers.filter((s) => s.id !== id);
      state = {
        ...state,
        servers: remaining,
        activeServerId: state.activeServerId === id ? remaining[0]!.id : state.activeServerId,
      };
      emit();
    },

    // ── LLM config ──────────────────────────────────────────
    llm: state.llm,
    setLLM: (patch: Partial<LLMConfig>) => {
      state = { ...state, llm: { ...state.llm, ...patch } };
      emit();
    },

    // ── Conversations ───────────────────────────────────────
    conversations: state.conversations,
    activeConversationId: state.activeConversationId,
    activeConversation:
      state.conversations.find((c) => c.id === state.activeConversationId) ?? null,
    newConversation: (): string => {
      const id = genId("conv");
      const now = Date.now();
      state = {
        ...state,
        conversations: [
          {
            id,
            title: "New chat",
            messages: [],
            createdAt: now,
            updatedAt: now,
          },
          ...state.conversations,
        ],
        activeConversationId: id,
      };
      emit();
      return id;
    },
    selectConversation: (id: string) => {
      state = { ...state, activeConversationId: id };
      emit();
    },
    deleteConversation: (id: string) => {
      const remaining = state.conversations.filter((c) => c.id !== id);
      state = {
        ...state,
        conversations: remaining,
        activeConversationId:
          state.activeConversationId === id ? (remaining[0]?.id ?? null) : state.activeConversationId,
      };
      emit();
    },
    updateConversation: (id: string, patch: Partial<Conversation>) => {
      state = {
        ...state,
        conversations: state.conversations.map((c) =>
          c.id === id ? { ...c, ...patch, updatedAt: Date.now() } : c,
        ),
      };
      emit();
    },
    appendMessage: (convId: string, msg: ChatMessage) => {
      state = {
        ...state,
        conversations: state.conversations.map((c) =>
          c.id === convId
            ? { ...c, messages: [...c.messages, msg], updatedAt: Date.now() }
            : c,
        ),
      };
      emit();
    },
    updateMessage: (convId: string, msgId: string, patch: Partial<ChatMessage>) => {
      state = {
        ...state,
        conversations: state.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) => (m.id === msgId ? { ...m, ...patch } : m)),
                updatedAt: Date.now(),
              }
            : c,
        ),
      };
      emit();
    },

    // ── util ────────────────────────────────────────────────
    genId,
  };
}
