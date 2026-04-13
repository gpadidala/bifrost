// Built-in chat agent — works without any LLM key.
//
// This is a deterministic intent matcher. It recognizes common questions
// about Grafana state (dashboards, datasources, folders, alerts, health,
// users) and routes them directly to Bifröst MCP tools, then formats the
// result as readable Markdown-ish text.
//
// No LLM, no API key, no network hop to Anthropic/OpenAI. Every response
// comes from the live Grafana via the Bifröst REST bridge, so role
// enforcement, pooling, and retry all apply.
//
// If none of the intents match, we fall back to a help message that
// lists everything the built-in agent knows how to do.

import type { BifrostClient } from "./api";
import type { StreamRequest } from "./llm";

// ─────────────────────────────────────────────────────────────────────────────
// Intent definitions
// ─────────────────────────────────────────────────────────────────────────────

interface Intent {
  name: string;
  /** One of these must match for the intent to fire */
  match: RegExp[];
  /** Tool name to invoke via the bridge */
  tool: string;
  /** Build arguments from the user message */
  args?: (text: string) => Record<string, unknown>;
  /** Format the tool result into a human-readable string */
  format: (result: any, text: string) => string;
}

const INTENTS: Intent[] = [
  // ── Dashboards ──────────────────────────────────────────────────────────
  {
    name: "list-dashboards",
    match: [
      /list (all )?dashboards?/i,
      /show (all|me|the)? ?dashboards?/i,
      /what dashboards/i,
      /all dashboards/i,
      /how many dashboards/i,
      /dashboards?\s+(tagged|with tag|tag:)/i,
      /dashboards?\s+in (the )?folder/i,
    ],
    tool: "list_dashboards",
    args: (text) => {
      const a: Record<string, unknown> = { limit: 500 };
      const tagMatch = text.match(/tag(?:ged|:|s?\s+with)\s+["']?([\w\- ]+?)["']?\s*$/i);
      if (tagMatch?.[1]) a.tags = [tagMatch[1].trim()];
      return a;
    },
    format: (result: any[], text) => {
      if (!result || result.length === 0) return "No dashboards found.";
      const countQ = /how many/i.test(text);
      if (countQ) {
        const byFolder: Record<string, number> = {};
        for (const d of result) {
          const f = d.folder_title || "General";
          byFolder[f] = (byFolder[f] || 0) + 1;
        }
        const top = Object.entries(byFolder)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 10)
          .map(([f, n]) => `- **${f}** — ${n}`)
          .join("\n");
        return `**${result.length} dashboards** across **${Object.keys(byFolder).length} folders**.\n\nTop folders:\n${top}`;
      }
      const limit = 25;
      const lines = result.slice(0, limit).map((d: any) => {
        const tags = (d.tags && d.tags.length ? ` · _${d.tags.slice(0, 3).join(", ")}_` : "");
        return `- **${d.title}** · ${d.folder_title || "General"}${tags}`;
      });
      const more = result.length > limit ? `\n\n_…and ${result.length - limit} more — try **\"search dashboards <term>\"** to narrow it down_` : "";
      return `Found **${result.length}** dashboards:\n\n${lines.join("\n")}${more}`;
    },
  },
  {
    name: "search-dashboards",
    match: [/search dashboards?\s+(?:for\s+)?(.+)/i, /find dashboards?\s+(?:for\s+)?(.+)/i, /dashboards?\s+(?:about|matching|named)\s+(.+)/i],
    tool: "search_dashboards",
    args: (text) => {
      const m = text.match(/(?:search|find|about|matching|named)\s+(?:dashboards?\s+)?(?:for\s+)?(.+)$/i);
      const query = m?.[1]?.trim().replace(/[?!.]+$/, "") ?? "";
      return { query, limit: 100 };
    },
    format: (result: any[], _text) => {
      if (!result || result.length === 0) return "No dashboards matched.";
      const lines = result.slice(0, 30).map((d: any) => `- **${d.title}** · ${d.folder_title || "General"} · \`${d.uid}\``);
      const more = result.length > 30 ? `\n\n_…and ${result.length - 30} more_` : "";
      return `**${result.length}** dashboards match:\n\n${lines.join("\n")}${more}`;
    },
  },
  // ── Datasources ─────────────────────────────────────────────────────────
  {
    name: "list-datasources",
    match: [/list (all )?datasources?/i, /show (all|me|the)? ?datasources?/i, /what datasources?/i, /which datasources?/i, /(all|how many) datasources?/i],
    tool: "list_datasources",
    format: (result: any[], _text) => {
      if (!result || result.length === 0) return "No datasources configured.";
      const byType: Record<string, number> = {};
      for (const d of result) byType[d.type] = (byType[d.type] || 0) + 1;
      const lines = result.map((d: any) => {
        const def = d.is_default ? " · **default**" : "";
        return `- **${d.name}** · \`${d.type}\`${def} · ${d.url || "—"}`;
      });
      const typeSummary = Object.entries(byType).map(([t, n]) => `${n} × ${t}`).join(", ");
      return `**${result.length}** datasources (${typeSummary}):\n\n${lines.join("\n")}`;
    },
  },
  // ── Folders ─────────────────────────────────────────────────────────────
  {
    name: "list-folders",
    match: [/list (all )?folders?/i, /show (all|me|the)? ?folders?/i, /what folders?/i, /folder (structure|tree|hierarchy)/i, /how many folders?/i],
    tool: "list_folders",
    format: (result: any[], _text) => {
      if (!result || result.length === 0) return "No folders.";
      const lines = result.map((f: any) => `- **${f.title}** · \`${f.uid}\``);
      return `**${result.length}** folders:\n\n${lines.join("\n")}`;
    },
  },
  // ── Alerts ──────────────────────────────────────────────────────────────
  {
    name: "list-alert-rules",
    match: [/list (all )?alert rules?/i, /show (all|me|the)? ?alert rules?/i, /what alert rules?/i],
    tool: "list_alert_rules",
    format: (result: any[], _text) => {
      if (!result || result.length === 0) return "No alert rules configured.";
      const lines = result.slice(0, 30).map((r: any) => `- **${r.title}** · state: \`${r.state || "unknown"}\` · \`${r.uid}\``);
      const more = result.length > 30 ? `\n\n_…and ${result.length - 30} more_` : "";
      return `**${result.length}** alert rules:\n\n${lines.join("\n")}${more}`;
    },
  },
  {
    name: "list-firing-alerts",
    match: [/firing alerts?/i, /what.*alerts? .* firing/i, /any.*alerts? .* firing/i, /alerts? .* right now/i, /active alerts?/i, /current alerts?/i],
    tool: "list_alert_instances",
    format: (result: any[], _text) => {
      if (!result) return "Could not fetch alert instances.";
      const firing = result.filter((a: any) => {
        const st = String(a.status ?? a.state ?? "").toLowerCase();
        return st.includes("firing") || st === "alerting";
      });
      if (firing.length === 0) {
        return `✓ **No firing alerts** — all quiet. _(checked ${result.length} alert instances)_`;
      }
      const lines = firing.slice(0, 20).map((a: any) => {
        const labels = Object.entries(a.labels || {}).slice(0, 3).map(([k, v]) => `${k}=${v}`).join(" ");
        return `- 🔥 **${a.rule_title || a.fingerprint || "alert"}** · ${labels}`;
      });
      const more = firing.length > 20 ? `\n\n_…and ${firing.length - 20} more firing_` : "";
      return `⚠️ **${firing.length} alerts firing** _(of ${result.length} total)_:\n\n${lines.join("\n")}${more}`;
    },
  },
  // ── Users ───────────────────────────────────────────────────────────────
  {
    name: "list-users",
    match: [/list (all )?users?/i, /show (all|me|the)? ?users?/i, /who.*users?/i, /how many users?/i],
    tool: "list_users",
    format: (result: any[], _text) => {
      if (!result) return "Users list requires admin role on the active environment.";
      if (result.length === 0) return "No users.";
      const byRole: Record<string, number> = {};
      for (const u of result) byRole[u.role] = (byRole[u.role] || 0) + 1;
      const roleSummary = Object.entries(byRole).map(([r, n]) => `${n} × ${r}`).join(", ");
      const lines = result.slice(0, 20).map((u: any) => `- **${u.login}** · ${u.role} · ${u.email}`);
      const more = result.length > 20 ? `\n\n_…and ${result.length - 20} more_` : "";
      return `**${result.length}** users (${roleSummary}):\n\n${lines.join("\n")}${more}`;
    },
  },
  // ── Health ──────────────────────────────────────────────────────────────
  {
    name: "health-check",
    match: [/health/i, /is grafana .* (ok|up|healthy|alive)/i, /grafana status/i, /are you (ok|there|alive)/i, /ping/i],
    tool: "health_check",
    format: (result: any, _text) => {
      if (!result) return "No response from Grafana.";
      const db = result.database || "unknown";
      const ver = result.version || "unknown";
      const ok = db === "ok";
      return `${ok ? "✓" : "✗"} **Grafana ${ver}** · database: \`${db}\` · commit: \`${(result.commit || "").slice(0, 10)}\``;
    },
  },
  // ── Server info ─────────────────────────────────────────────────────────
  {
    name: "server-info",
    match: [/server info/i, /what.*connected/i, /what environment/i, /what role/i, /bifrost info/i, /(current|active) (env|environment|role)/i],
    tool: "get_server_info",
    format: (result: any, _text) => {
      if (!result) return "No server info.";
      const lines = Object.entries(result).map(([k, v]) => `- **${k}**: \`${v}\``);
      return `Bifröst server info:\n\n${lines.join("\n")}`;
    },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Tool invocation helper
// ─────────────────────────────────────────────────────────────────────────────

async function callToolViaBridge(
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
    const env = (await r.json()) as { ok: true; data: unknown } | { ok: false; error: string; message: string };
    const durationMs = Math.round(performance.now() - t0);
    if (!env.ok) return { result: null, error: `${env.error}: ${env.message}`, durationMs };
    return { result: env.data, durationMs };
  } catch (err) {
    return { result: null, error: err instanceof Error ? err.message : String(err), durationMs: Math.round(performance.now() - t0) };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Intent matcher
// ─────────────────────────────────────────────────────────────────────────────

function matchIntent(text: string): Intent | null {
  for (const intent of INTENTS) {
    for (const re of intent.match) {
      if (re.test(text)) return intent;
    }
  }
  return null;
}

function helpMessage(): string {
  return (
    "**Built-in Bifröst agent** — I route questions straight to MCP tools without needing an LLM.\n\n" +
    "I can answer:\n" +
    "- **Dashboards** — \"list dashboards\", \"how many dashboards\", \"search dashboards for kafka\", \"dashboards tagged production\"\n" +
    "- **Datasources** — \"list datasources\", \"what datasources\"\n" +
    "- **Folders** — \"list folders\", \"folder structure\"\n" +
    "- **Alerts** — \"list alert rules\", \"any firing alerts\", \"what's firing right now\"\n" +
    "- **Users** — \"list users\", \"how many users\" _(admin role)_\n" +
    "- **Health** — \"health\", \"is grafana ok\", \"ping\"\n" +
    "- **Server** — \"server info\", \"current environment\"\n\n" +
    "For free-form questions and multi-step reasoning, add an **Anthropic** or **OpenAI** key in **⚙ Settings → LLM** to upgrade."
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Public entry — used by runChat when provider === "builtin"
// ─────────────────────────────────────────────────────────────────────────────

function emitText(onEvent: StreamRequest["onEvent"], text: string): void {
  // Chunk the text into ~8-char pieces so the UI shows a "streaming" feel
  const chunkSize = 12;
  for (let i = 0; i < text.length; i += chunkSize) {
    onEvent({ type: "text", delta: text.slice(i, i + chunkSize) });
  }
}

export async function runBuiltin(req: StreamRequest): Promise<void> {
  const { messages, bridge, onEvent, signal } = req;
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  if (!lastUser) {
    onEvent({ type: "done" });
    return;
  }
  const text = lastUser.content.trim();

  // Unmatched / empty → help
  const intent = matchIntent(text);
  if (!intent) {
    emitText(onEvent, helpMessage());
    onEvent({ type: "done" });
    return;
  }

  if (signal?.aborted) return;

  // Build args and surface the tool call as a card
  const args = intent.args ? intent.args(text) : {};
  const callId = `builtin-${Date.now()}`;
  onEvent({ type: "tool_start", id: callId, name: intent.tool, input: args });

  const { result, error, durationMs } = await callToolViaBridge(bridge, intent.tool, args);
  onEvent({ type: "tool_result", id: callId, result, error, durationMs });

  if (error) {
    emitText(onEvent, `I tried to run \`${intent.tool}\` but it failed:\n\n> ${error}\n\n_If this is a role issue, try switching the active role in the header (viewer / editor / admin)._`);
    onEvent({ type: "done" });
    return;
  }

  try {
    const formatted = intent.format(result, text);
    emitText(onEvent, formatted);
  } catch (err) {
    emitText(
      onEvent,
      `I called \`${intent.tool}\` successfully but couldn't format the result:\n\n${err instanceof Error ? err.message : String(err)}`,
    );
  }

  onEvent({ type: "done" });
}

export const BUILTIN_HELP = helpMessage;
