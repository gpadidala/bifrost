import { useCallback, useEffect, useRef, useState } from "react";
import type { BifrostClient } from "./api";
import { fetchToolCatalog, runChat, type LLMEvent, type MCPToolDef } from "./llm";
import {
  usePersistedStore,
  type ChatMessage,
  type Conversation,
  type ToolCall,
} from "./store";

interface ChatProps {
  client: BifrostClient;
}

export function ChatPage({ client }: ChatProps) {
  const store = usePersistedStore();
  const [tools, setTools] = useState<MCPToolDef[]>([]);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Fetch tool catalog whenever the MCP server changes
  useEffect(() => {
    let cancelled = false;
    setToolsError(null);
    fetchToolCatalog(client)
      .then((t) => {
        if (!cancelled) setTools(t);
      })
      .catch((err) => {
        if (!cancelled) setToolsError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const activeConv = store.activeConversation;
  // Built-in provider needs no key; hosted providers need a key
  const llmReady = store.llm.provider === "builtin" || store.llm.apiKey.trim().length > 0;

  const ensureConv = useCallback((): string => {
    if (store.activeConversationId) return store.activeConversationId;
    return store.newConversation();
  }, [store]);

  const send = async () => {
    if (!input.trim() || !llmReady || sending) return;
    const userText = input.trim();
    setInput("");
    setSending(true);

    const convId = ensureConv();
    const userMsg: ChatMessage = {
      id: store.genId("msg"),
      role: "user",
      content: userText,
      createdAt: Date.now(),
    };
    store.appendMessage(convId, userMsg);

    // Title the convo from the first user message
    const conv = store.conversations.find((c) => c.id === convId);
    if (conv && conv.messages.length === 0) {
      store.updateConversation(convId, { title: userText.slice(0, 60) });
    }

    const assistantId = store.genId("msg");
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      toolCalls: [],
      createdAt: Date.now(),
      streaming: true,
    };
    store.appendMessage(convId, assistantMsg);

    // Build the full message history for the LLM from the store
    const currentConv =
      store.conversations.find((c) => c.id === convId) ?? ({ messages: [userMsg] } as Conversation);
    const history = currentConv.messages
      .filter((m) => m.id !== assistantId)
      .map((m) => ({ role: m.role, content: m.content }));

    const controller = new AbortController();
    abortRef.current = controller;

    let streamed = "";
    const toolCalls: ToolCall[] = [];

    try {
      await runChat({
        config: store.llm,
        tools,
        messages: history,
        bridge: client,
        signal: controller.signal,
        onEvent: (evt: LLMEvent) => {
          if (evt.type === "text") {
            streamed += evt.delta;
            store.updateMessage(convId, assistantId, { content: streamed });
          } else if (evt.type === "tool_start") {
            toolCalls.push({
              id: evt.id,
              name: evt.name,
              input: evt.input,
              status: "pending",
            });
            store.updateMessage(convId, assistantId, { toolCalls: [...toolCalls] });
          } else if (evt.type === "tool_result") {
            const idx = toolCalls.findIndex((t) => t.id === evt.id);
            if (idx >= 0) {
              toolCalls[idx] = {
                ...toolCalls[idx]!,
                result: evt.result,
                error: evt.error,
                durationMs: evt.durationMs,
                status: evt.error ? "error" : "ok",
              };
              store.updateMessage(convId, assistantId, { toolCalls: [...toolCalls] });
            }
          } else if (evt.type === "error") {
            streamed += `\n\n**Error:** ${evt.message}`;
            store.updateMessage(convId, assistantId, {
              content: streamed,
              streaming: false,
            });
          }
        },
      });
      store.updateMessage(convId, assistantId, { content: streamed, streaming: false });
    } catch (err) {
      store.updateMessage(convId, assistantId, {
        content: streamed + `\n\n**Stream error:** ${err instanceof Error ? err.message : String(err)}`,
        streaming: false,
      });
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSending(false);
  };

  return (
    <div className="chat">
      <aside className="chat-sidebar">
        <button className="btn primary" style={{ width: "100%" }} onClick={() => store.newConversation()}>
          + New chat
        </button>
        <div className="conv-list">
          {store.conversations.length === 0 && (
            <div className="muted mono" style={{ padding: 12, fontSize: 11, textAlign: "center" }}>
              No conversations yet
            </div>
          )}
          {store.conversations.map((c) => (
            <div
              key={c.id}
              className={`conv-row ${c.id === store.activeConversationId ? "active" : ""}`}
              onClick={() => store.selectConversation(c.id)}
            >
              <div className="conv-title">{c.title || "Untitled"}</div>
              <div className="conv-meta">
                {c.messages.length} msg · {formatTimeAgo(c.updatedAt)}
              </div>
              <button
                className="conv-del"
                onClick={(e) => {
                  e.stopPropagation();
                  store.deleteConversation(c.id);
                }}
                aria-label="Delete conversation"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="chat-main">
        {store.llm.provider === "builtin" && (
          <div className="banner" style={{ background: "var(--cyan-dim)", borderColor: "#22d3ee55" }}>
            <strong style={{ color: "var(--cyan)" }}>Built-in agent active.</strong> No LLM key needed — questions are routed directly to MCP tools. For free-form reasoning, switch to Anthropic or OpenAI in{" "}
            <button
              className="btn ghost"
              style={{ padding: "2px 10px", fontSize: 12 }}
              onClick={() => document.querySelector<HTMLButtonElement>(".icon-btn[aria-label=Settings]")?.click()}
            >
              ⚙ Settings
            </button>
            .
          </div>
        )}
        {store.llm.provider !== "builtin" && !llmReady && (
          <div className="banner">
            <strong>No LLM key configured.</strong> Open{" "}
            <button
              className="btn ghost"
              style={{ padding: "2px 10px", fontSize: 12 }}
              onClick={() => document.querySelector<HTMLButtonElement>(".icon-btn[aria-label=Settings]")?.click()}
            >
              ⚙ Settings
            </button>{" "}
            → <em>LLM</em> to add an Anthropic or OpenAI key — or switch back to the built-in agent. Keys live in your browser; the Bifröst backend never sees them.
          </div>
        )}
        {toolsError && (
          <div className="banner err">
            <strong>Tool catalog unreachable:</strong> {toolsError}
          </div>
        )}

        <div className="messages">
          {!activeConv || activeConv.messages.length === 0 ? (
            <EmptyHero
              provider={store.llm.provider}
              llmReady={llmReady}
              toolCount={tools.length}
              llmModel={store.llm.model}
            />
          ) : (
            activeConv.messages.map((m) => <MessageView key={m.id} msg={m} />)
          )}
        </div>

        <div className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={
              llmReady
                ? "Ask about dashboards, datasources, alerts… (⏎ to send, ⇧⏎ newline)"
                : "Add an LLM key in Settings to start chatting"
            }
            disabled={!llmReady || sending}
            rows={3}
          />
          {sending ? (
            <button className="btn danger" onClick={cancel}>
              Stop
            </button>
          ) : (
            <button className="btn primary" onClick={send} disabled={!llmReady || !input.trim()}>
              Send
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

function EmptyHero({
  provider,
  llmReady,
  toolCount,
  llmModel,
}: {
  provider: "builtin" | "anthropic" | "openai";
  llmReady: boolean;
  toolCount: number;
  llmModel: string;
}) {
  const builtin = provider === "builtin";
  return (
    <div className="chat-hero">
      <h2>{builtin ? "Ask Grafana — no key needed." : "Ask Grafana anything."}</h2>
      <p className="muted">
        {builtin ? (
          <>
            Built-in agent routes your questions directly to <strong>{toolCount}</strong> Bifröst MCP tools. Works
            offline, instant, no keys. Upgrade to Claude or GPT in Settings for free-form reasoning.
          </>
        ) : (
          <>
            The LLM has <strong>{toolCount}</strong> Bifröst MCP tools on tap —{" "}
            {llmReady ? (
              <>using <span className="mono">{llmModel}</span>.</>
            ) : (
              <>add a key in Settings first.</>
            )}
          </>
        )}
      </p>
      <div className="suggestions">
        <Suggestion text="List all dashboards" />
        <Suggestion text="How many dashboards are there?" />
        <Suggestion text="Search dashboards for kafka" />
        <Suggestion text="List datasources" />
        <Suggestion text="What folders exist?" />
        <Suggestion text="Are there any firing alerts?" />
        <Suggestion text="Is Grafana healthy?" />
        <Suggestion text="Dashboards tagged production" />
      </div>
    </div>
  );
}

function Suggestion({ text }: { text: string }) {
  return (
    <div
      className="suggestion"
      onClick={() => {
        const ta = document.querySelector<HTMLTextAreaElement>(".composer textarea");
        if (ta) {
          ta.value = text;
          ta.dispatchEvent(new Event("input", { bubbles: true }));
          ta.focus();
        }
      }}
    >
      {text}
    </div>
  );
}

function MessageView({ msg }: { msg: ChatMessage }) {
  return (
    <div className={`msg ${msg.role}`}>
      <div className="msg-avatar">{msg.role === "user" ? "U" : "B"}</div>
      <div className="msg-body">
        <div className="msg-role">{msg.role}</div>
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="tool-calls">
            {msg.toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} call={tc} />
            ))}
          </div>
        )}
        <div className="msg-text">
          {msg.content || (msg.streaming ? <span className="cursor">▋</span> : null)}
          {msg.streaming && msg.content && <span className="cursor">▋</span>}
        </div>
      </div>
    </div>
  );
}

function ToolCallCard({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const statusClass = call.status === "ok" ? "ok" : call.status === "error" ? "err" : "pending";
  return (
    <div className={`tool-call ${statusClass}`}>
      <button className="tool-call-header" onClick={() => setOpen((o) => !o)}>
        <span className={`tool-dot ${statusClass}`} />
        <span className="tool-name">{call.name}</span>
        <span className="tool-meta">
          {call.status === "pending" && "running…"}
          {call.status === "ok" && `${call.durationMs}ms`}
          {call.status === "error" && "error"}
        </span>
        <span className="tool-caret">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="tool-call-body">
          <div className="tool-section">
            <div className="tool-section-label">input</div>
            <pre>{JSON.stringify(call.input, null, 2)}</pre>
          </div>
          {call.result !== undefined && (
            <div className="tool-section">
              <div className="tool-section-label">result</div>
              <pre>{trimJson(JSON.stringify(call.result, null, 2))}</pre>
            </div>
          )}
          {call.error && (
            <div className="tool-section">
              <div className="tool-section-label">error</div>
              <pre className="err">{call.error}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function trimJson(s: string, max = 4000): string {
  if (s.length <= max) return s;
  return s.slice(0, max) + `\n\n… truncated (${s.length - max} more chars)`;
}

function formatTimeAgo(ts: number): string {
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}
