import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  makeClient,
  type BifrostClient,
  type DashboardSummary,
  type Datasource,
  type EnvName,
  type EnvTestResult,
  type EnvironmentDescriptor,
  type Folder,
  type HealthStatus,
  type RoleName,
  type ServerInfo,
} from "./api";
import { ChatPage } from "./Chat";
import { usePersistedStore, type LLMConfig, type LLMProvider } from "./store";

type Tab = "overview" | "chat" | "dashboards" | "datasources" | "folders";

const ANTHROPIC_MODELS = [
  "claude-opus-4-5",
  "claude-sonnet-4-5-20250929",
  "claude-sonnet-4-20250514",
  "claude-haiku-4-5",
];
const OPENAI_MODELS = ["gpt-4o", "gpt-4o-mini", "o3", "o4-mini"];

interface Toast {
  id: number;
  kind: "ok" | "err" | "info";
  msg: string;
}

const ENVS: EnvName[] = ["dev", "perf", "prod"];
const ROLES: RoleName[] = ["viewer", "editor", "admin"];

export function App() {
  const store = usePersistedStore();
  const client = useMemo<BifrostClient>(() => makeClient(store.activeServer.url), [store.activeServer.url]);

  const [tab, setTab] = useState<Tab>("overview");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [info, setInfo] = useState<ServerInfo | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [dashboards, setDashboards] = useState<DashboardSummary[]>([]);
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  const pushToast = useCallback((kind: Toast["kind"], msg: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, kind, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, []);

  // Load everything from the active server whenever it changes or data is refreshed
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const i = await client.serverInfo();
      setInfo(i);
      const [h, d, ds, f] = await Promise.all([
        client.health().catch(() => null),
        client.dashboards().catch(() => []),
        client.datasources().catch(() => []),
        client.folders().catch(() => []),
      ]);
      setHealth(h);
      setDashboards(d);
      setDatasources(ds);
      setFolders(f);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const switchEnv = async (env: EnvName) => {
    try {
      await client.setActive({ environment: env });
      pushToast("ok", `Switched to ${env.toUpperCase()}`);
      await refresh();
    } catch (err) {
      pushToast("err", err instanceof Error ? err.message : String(err));
    }
  };

  const switchRole = async (role: RoleName) => {
    try {
      await client.setActive({ role });
      pushToast("ok", `Role → ${role}`);
      await refresh();
    } catch (err) {
      pushToast("err", err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="logo" />
          Bifröst <span className="version">v{info?.version ?? "…"}</span>
        </div>

        {info && (
          <div className="env-tabs" role="tablist" aria-label="Active environment">
            {ENVS.map((e) => {
              const cfg = info.environments[e];
              const configured = cfg && (cfg.has_viewer || cfg.has_editor || cfg.has_admin);
              const active = info.active_environment === e;
              return (
                <button
                  key={e}
                  className={`env-tab ${active ? "active" : ""} ${configured ? "configured" : "unconfigured"}`}
                  onClick={() => switchEnv(e)}
                  title={configured ? cfg!.base_url : "not configured — open Settings"}
                >
                  <span className="dot" />
                  {e}
                </button>
              );
            })}
          </div>
        )}

        {info && (
          <div className="role-selector" aria-label="Active role">
            {ROLES.map((r) => {
              const cfg = info.environments[info.active_environment];
              const hasToken = cfg ? cfg[`has_${r}` as keyof EnvironmentDescriptor] : false;
              const active = info.active_role === r;
              return (
                <button
                  key={r}
                  data-role={r}
                  className={`role-btn ${active ? "active" : ""}`}
                  disabled={!hasToken}
                  onClick={() => switchRole(r)}
                  title={hasToken ? `Use ${r} token` : `No ${r} token configured`}
                >
                  {r}
                </button>
              );
            })}
          </div>
        )}

        <div className="spacer" />

        <MCPServerPicker />

        <div className="header-actions">
          <button
            className="icon-btn"
            onClick={() => refresh()}
            title="Refresh"
            aria-label="Refresh"
          >
            ↻
          </button>
          <button
            className={`icon-btn ${settingsOpen ? "active" : ""}`}
            onClick={() => setSettingsOpen(true)}
            title="Settings"
            aria-label="Settings"
          >
            ⚙
          </button>
        </div>
      </header>

      <aside className="sidebar">
        <h2>Workspace</h2>
        <button className={`nav-item ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>
          <span className="icon">◆</span>Overview
        </button>
        <button className={`nav-item ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")}>
          <span className="icon">✦</span>AI Chat
          {store.llm.apiKey ? (
            <span className="count">{store.llm.provider === "anthropic" ? "C" : "O"}</span>
          ) : (
            <span className="count" style={{ color: "var(--err)" }}>!</span>
          )}
        </button>
        <h2>Resources</h2>
        <button className={`nav-item ${tab === "dashboards" ? "active" : ""}`} onClick={() => setTab("dashboards")}>
          <span className="icon">▦</span>Dashboards <span className="count">{dashboards.length}</span>
        </button>
        <button className={`nav-item ${tab === "datasources" ? "active" : ""}`} onClick={() => setTab("datasources")}>
          <span className="icon">◈</span>Datasources <span className="count">{datasources.length}</span>
        </button>
        <button className={`nav-item ${tab === "folders" ? "active" : ""}`} onClick={() => setTab("folders")}>
          <span className="icon">▸</span>Folders <span className="count">{folders.length}</span>
        </button>

        <h2>Quick actions</h2>
        <button className="nav-item" onClick={() => setSettingsOpen(true)}>
          <span className="icon">⚙</span>Configure environments
        </button>
        <button className="nav-item" onClick={() => refresh()}>
          <span className="icon">↻</span>Refresh everything
        </button>

        <div className="sidebar-footer">
          <div className="row">
            <span>mcp server</span>
            <strong>{store.activeServer.label}</strong>
          </div>
          <div className="row">
            <span>transport</span>
            <strong>{info?.transport.mode ?? "—"}</strong>
          </div>
          <div className="row">
            <span>port</span>
            <strong>{info?.transport.port ?? "—"}</strong>
          </div>
          <div className="row">
            <span>grafana</span>
            <strong>{health ? `v${health.version}` : "—"}</strong>
          </div>
        </div>
      </aside>

      <main className="main" style={tab === "chat" ? { padding: 0, overflow: "hidden" } : undefined}>
        {tab !== "chat" && (
          <>
            <h1 className="page-title">
              {tab === "overview" && "Overview"}
              {tab === "dashboards" && "Dashboards"}
              {tab === "datasources" && "Datasources"}
              {tab === "folders" && "Folders"}
            </h1>
            <p className="page-sub">
              Connected to <span className="mono">{store.activeServer.url}</span> ·{" "}
              <span className="mono">{info?.active_environment ?? "—"}</span> /{" "}
              <span className="mono">{info?.active_role ?? "—"}</span>
              {health && (
                <>
                  {" · "}
                  <span className="mono">Grafana {health.version}</span>
                </>
              )}
            </p>
          </>
        )}

        {error && <div className="error-box">✗ {error}</div>}
        {loading && !info && <div className="loading">Loading Bifröst state…</div>}

        {info && tab === "overview" && (
          <OverviewTab info={info} health={health} dashboards={dashboards} datasources={datasources} folders={folders} />
        )}
        {tab === "chat" && <ChatPage client={client} />}
        {info && tab === "dashboards" && <DashboardsTab dashboards={dashboards} />}
        {info && tab === "datasources" && <DatasourcesTab datasources={datasources} />}
        {info && tab === "folders" && <FoldersTab folders={folders} />}
      </main>

      {settingsOpen && info && (
        <SettingsDrawer
          info={info}
          client={client}
          store={store}
          onClose={() => setSettingsOpen(false)}
          onRefresh={refresh}
          toast={pushToast}
        />
      )}

      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP server picker — dropdown in the header
// ─────────────────────────────────────────────────────────────────────────────

function MCPServerPicker() {
  const store = usePersistedStore();
  return (
    <div className="mcp-picker" title={store.activeServer.url}>
      <span className="dot" />
      <select
        value={store.activeServerId}
        onChange={(e) => store.setActiveServer(e.target.value)}
        aria-label="MCP server"
      >
        {store.servers.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Overview tab
// ─────────────────────────────────────────────────────────────────────────────

function OverviewTab({
  info,
  health,
  dashboards,
  datasources,
  folders,
}: {
  info: ServerInfo;
  health: HealthStatus | null;
  dashboards: DashboardSummary[];
  datasources: Datasource[];
  folders: Folder[];
}) {
  const active = info.environments[info.active_environment];
  const tagCount = useMemo(
    () => new Set(dashboards.flatMap((d) => d.tags ?? [])).size,
    [dashboards],
  );

  return (
    <>
      <div className="stats-row">
        <div className="stat accent">
          <div className="label">Active environment</div>
          <div className="value">{info.active_environment.toUpperCase()}</div>
          <div className="sub">{info.active_role}</div>
        </div>
        <div className="stat ok">
          <div className="label">Grafana</div>
          <div className="value">{health ? `v${health.version}` : "—"}</div>
          <div className="sub">{health ? health.database : "disconnected"}</div>
        </div>
        <div className="stat cyan">
          <div className="label">Dashboards</div>
          <div className="value">{dashboards.length}</div>
          <div className="sub">{tagCount} unique tags</div>
        </div>
        <div className="stat violet">
          <div className="label">Folders</div>
          <div className="value">{folders.length}</div>
          <div className="sub">&nbsp;</div>
        </div>
        <div className="stat pink">
          <div className="label">Datasources</div>
          <div className="value">{datasources.length}</div>
          <div className="sub">&nbsp;</div>
        </div>
      </div>

      <div className="card-grid">
        <div className="card">
          <h3>
            Connection <span className="muted">· {info.active_environment}</span>
          </h3>
          <dl className="kv">
            <dt>Bifröst</dt>
            <dd>v{info.version}</dd>
            <dt>Transport</dt>
            <dd>
              {info.transport.mode} · :{info.transport.port} · {info.transport.path_prefix}
            </dd>
            <dt>Grafana URL</dt>
            <dd>{active?.base_url ?? "—"}</dd>
            <dt>TLS verify</dt>
            <dd>{active?.tls_verify ? "yes" : "no"}</dd>
            <dt>Timeout</dt>
            <dd>{active?.timeout_seconds ?? "—"} s</dd>
            <dt>Rate limit</dt>
            <dd>{active?.rate_limit_rps ?? "—"} rps</dd>
            {health && (
              <>
                <dt>Grafana version</dt>
                <dd>{health.version}</dd>
                <dt>Database</dt>
                <dd>{health.database}</dd>
                <dt>Commit</dt>
                <dd>{health.commit}</dd>
              </>
            )}
          </dl>
        </div>

        <div className="card">
          <h3>Token availability</h3>
          <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
            Per-environment · per-role. Configure in{" "}
            <button
              className="btn ghost"
              style={{ padding: "2px 8px", fontSize: 12 }}
              onClick={() => document.querySelector<HTMLButtonElement>(".icon-btn[aria-label=Settings]")?.click()}
            >
              ⚙ Settings
            </button>
          </p>
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
            <thead>
              <tr style={{ color: "var(--fg-2)", fontSize: 11, textTransform: "uppercase" }}>
                <th style={{ textAlign: "left", padding: "8px 4px" }}>env</th>
                <th style={{ textAlign: "center", padding: "8px 4px" }}>viewer</th>
                <th style={{ textAlign: "center", padding: "8px 4px" }}>editor</th>
                <th style={{ textAlign: "center", padding: "8px 4px" }}>admin</th>
              </tr>
            </thead>
            <tbody>
              {ENVS.map((e) => {
                const cfg = info.environments[e];
                const cell = (ok: boolean) => (
                  <td style={{ textAlign: "center", padding: "8px 4px" }}>
                    <span className={`badge ${ok ? "ok" : ""}`}>
                      <span className="dot" />
                      {ok ? "✓" : "—"}
                    </span>
                  </td>
                );
                return (
                  <tr key={e} style={{ borderTop: "1px solid var(--border-1)" }}>
                    <td className="mono" style={{ padding: "8px 4px", color: "var(--fg-1)" }}>
                      {e}
                    </td>
                    {cell(!!cfg?.has_viewer)}
                    {cell(!!cfg?.has_editor)}
                    {cell(!!cfg?.has_admin)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Dashboards / Datasources / Folders tabs
// ─────────────────────────────────────────────────────────────────────────────

function DashboardsTab({ dashboards }: { dashboards: DashboardSummary[] }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () =>
      q.trim() ? dashboards.filter((d) => d.title.toLowerCase().includes(q.toLowerCase())) : dashboards,
    [dashboards, q],
  );
  return (
    <div className="card">
      <h3>
        Live from Grafana <span className="muted">· {filtered.length} of {dashboards.length}</span>
      </h3>
      <input className="search" placeholder="filter by title…" value={q} onChange={(e) => setQ(e.target.value)} />
      {filtered.length === 0 ? (
        <div className="empty">No dashboards match.</div>
      ) : (
        <ul className="list">
          {filtered.slice(0, 300).map((d) => (
            <li key={d.uid}>
              <div className="row-icon">▦</div>
              <div>
                <div className="row-title">{d.title}</div>
                <div className="row-sub">{d.uid}</div>
              </div>
              <div className="row-right">
                {d.tags && d.tags.length > 0 && <span className="badge">{d.tags[0]}</span>}
                <span className="badge">{d.folder_title ?? "General"}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
      {filtered.length > 300 && <div className="muted mono" style={{ padding: 12, textAlign: "center" }}>…showing first 300</div>}
    </div>
  );
}

function DatasourcesTab({ datasources }: { datasources: Datasource[] }) {
  return (
    <div className="card">
      <h3>Live from Grafana</h3>
      {datasources.length === 0 ? (
        <div className="empty">No datasources configured in Grafana.</div>
      ) : (
        <ul className="list">
          {datasources.map((ds) => (
            <li key={ds.uid ?? ds.name}>
              <div className="row-icon">◈</div>
              <div>
                <div className="row-title">{ds.name}</div>
                <div className="row-sub">
                  {ds.type} · {ds.url ?? "—"}
                </div>
              </div>
              <div className="row-right">
                {ds.is_default && <span className="badge accent">default</span>}
                <span className="badge">{ds.type}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FoldersTab({ folders }: { folders: Folder[] }) {
  return (
    <div className="card">
      <h3>Live from Grafana</h3>
      {folders.length === 0 ? (
        <div className="empty">No folders yet.</div>
      ) : (
        <ul className="list">
          {folders.map((f) => (
            <li key={f.uid}>
              <div className="row-icon">▸</div>
              <div>
                <div className="row-title">{f.title}</div>
                <div className="row-sub">{f.uid}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings drawer — env CRUD + MCP server CRUD
// ─────────────────────────────────────────────────────────────────────────────

type Toaster = (kind: Toast["kind"], msg: string) => void;

function SettingsDrawer({
  info,
  client,
  store,
  onClose,
  onRefresh,
  toast,
}: {
  info: ServerInfo;
  client: BifrostClient;
  store: ReturnType<typeof usePersistedStore>;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  toast: Toaster;
}) {
  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Settings">
        <div className="drawer-header">
          <h2>Settings</h2>
          <div className="spacer" />
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="drawer-body">
          <LLMConfigSection />

          <hr style={{ border: "none", borderTop: "1px solid var(--border-1)", margin: "28px 0" }} />

          <h3 style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.09em", color: "var(--fg-2)", margin: "0 0 12px" }}>
            MCP Servers
          </h3>
          <p className="muted" style={{ fontSize: 12, marginTop: 0, marginBottom: 14 }}>
            Point the UI at one or more Bifröst MCP servers. Selected server is used for every request on this page.
          </p>

          <div className="server-list">
            {store.servers.map((s) => (
              <div key={s.id} className={`server-row ${s.id === store.activeServerId ? "active" : ""}`}>
                <div className="radio" onClick={() => store.setActiveServer(s.id)} role="radio" aria-checked={s.id === store.activeServerId} />
                <div className="body">
                  <div className="label">{s.label}</div>
                  <div className="url">{s.url}</div>
                </div>
                <button
                  className="btn danger ghost"
                  style={{ padding: "4px 10px", fontSize: 11 }}
                  disabled={store.servers.length <= 1}
                  onClick={() => store.removeServer(s.id)}
                >
                  remove
                </button>
              </div>
            ))}
          </div>

          <AddServerRow onAdd={(label, url) => store.addServer(label, url)} />

          <hr style={{ border: "none", borderTop: "1px solid var(--border-1)", margin: "28px 0" }} />

          <h3 style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.09em", color: "var(--fg-2)", margin: "0 0 4px" }}>
            Grafana environments
          </h3>
          <p className="muted" style={{ fontSize: 12, marginTop: 0, marginBottom: 18 }}>
            Per-environment Grafana URL and three role tokens. Changes apply to the live MCP server immediately (not persisted across restart — export or add to .env for durability).
          </p>

          {ENVS.map((e) => (
            <EnvCard
              key={e}
              env={e}
              config={info.environments[e]}
              client={client}
              onSaved={async () => {
                await onRefresh();
                toast("ok", `${e} saved`);
              }}
              toast={toast}
            />
          ))}
        </div>
      </aside>
    </>
  );
}

function AddServerRow({ onAdd }: { onAdd: (label: string, url: string) => void }) {
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
      <input
        className="search"
        style={{ flex: "0 0 140px", marginBottom: 0 }}
        placeholder="label"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />
      <input
        className="search"
        style={{ flex: 1, marginBottom: 0 }}
        placeholder="http://host:8765"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <button
        className="btn primary"
        disabled={!label || !url}
        onClick={() => {
          onAdd(label, url);
          setLabel("");
          setUrl("");
        }}
      >
        + Add
      </button>
    </div>
  );
}

function EnvCard({
  env,
  config,
  client,
  onSaved,
  toast,
}: {
  env: EnvName;
  config: EnvironmentDescriptor | undefined;
  client: BifrostClient;
  onSaved: () => Promise<void>;
  toast: Toaster;
}) {
  const [baseUrl, setBaseUrl] = useState(config?.base_url ?? "");
  const [tlsVerify, setTlsVerify] = useState(config?.tls_verify ?? true);
  const [timeoutS, setTimeoutS] = useState(config?.timeout_seconds ?? 30);
  const [rate, setRate] = useState(config?.rate_limit_rps ?? 10);
  const [viewer, setViewer] = useState("");
  const [editor, setEditor] = useState("");
  const [admin, setAdmin] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<EnvTestResult | null>(null);

  // Sync local state when the descriptor from server changes
  useEffect(() => {
    if (config) {
      setBaseUrl(config.base_url);
      setTlsVerify(config.tls_verify);
      setTimeoutS(config.timeout_seconds);
      setRate(config.rate_limit_rps);
    }
  }, [config]);

  const save = async () => {
    setSaving(true);
    try {
      const tokens: Record<string, string> = {};
      if (viewer) tokens.viewer = viewer;
      if (editor) tokens.editor = editor;
      if (admin) tokens.admin = admin;
      await client.updateEnv(env, {
        base_url: baseUrl,
        tls_verify: tlsVerify,
        timeout_seconds: timeoutS,
        rate_limit_rps: rate,
        service_accounts: Object.keys(tokens).length ? tokens : undefined,
      });
      setViewer("");
      setEditor("");
      setAdmin("");
      await onSaved();
    } catch (err) {
      toast("err", err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      const r = await client.testEnv(env);
      setResult(r);
      const okCount = Object.values(r.roles).filter((x) => x.status === "ok").length;
      toast(okCount > 0 ? "ok" : "err", `${env}: ${okCount}/3 roles reachable`);
    } catch (err) {
      toast("err", err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  };

  const tokenState = (role: RoleName): string => {
    if (!result) {
      const has = config?.[`has_${role}` as keyof EnvironmentDescriptor];
      return has ? "configured" : "missing";
    }
    const rr = result.roles[role];
    if (rr.status === "ok") return `${rr.latency_ms}ms`;
    if (rr.status === "missing") return "—";
    return "error";
  };

  const tokenStateClass = (role: RoleName): string => {
    if (!result) {
      const has = config?.[`has_${role}` as keyof EnvironmentDescriptor];
      return has ? "ok" : "missing";
    }
    const rr = result.roles[role];
    if (rr.status === "ok") return "ok";
    if (rr.status === "error") return "err";
    return "missing";
  };

  return (
    <div className="env-card">
      <div className="env-card-header">
        <span className={`title ${env}`}>● {env}</span>
        <div className="spacer" />
        {config && (config.has_viewer || config.has_editor || config.has_admin) && (
          <span className="badge ok">
            <span className="dot" />
            configured
          </span>
        )}
      </div>

      <div className="field">
        <label>Grafana URL</label>
        <input type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:3000" />
      </div>

      <div className="field-row">
        <div className="field">
          <label>TLS verify</label>
          <select
            value={tlsVerify ? "yes" : "no"}
            onChange={(e) => setTlsVerify(e.target.value === "yes")}
            style={{
              background: "var(--bg-2)",
              border: "1px solid var(--border-2)",
              borderRadius: 7,
              padding: "10px 13px",
              color: "var(--fg-0)",
              fontFamily: "var(--font-mono)",
              fontSize: 12.5,
            }}
          >
            <option value="yes">yes</option>
            <option value="no">no (dev only)</option>
          </select>
        </div>
        <div className="field">
          <label>Timeout (s)</label>
          <input type="number" value={timeoutS} onChange={(e) => setTimeoutS(Number(e.target.value))} />
        </div>
      </div>

      <div className="field">
        <label>Rate limit (rps)</label>
        <input type="number" value={rate} onChange={(e) => setRate(Number(e.target.value))} />
      </div>

      <div style={{ margin: "14px 0 4px", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--fg-2)", fontWeight: 600 }}>
        Service-account tokens
      </div>
      <p className="muted" style={{ fontSize: 11, margin: "0 0 10px" }}>
        Leave blank to keep the existing value. Type a new token to overwrite.
      </p>

      <TokenField role="viewer" value={viewer} onChange={setViewer} state={tokenState("viewer")} stateClass={tokenStateClass("viewer")} />
      <TokenField role="editor" value={editor} onChange={setEditor} state={tokenState("editor")} stateClass={tokenStateClass("editor")} />
      <TokenField role="admin" value={admin} onChange={setAdmin} state={tokenState("admin")} stateClass={tokenStateClass("admin")} />

      <div className="env-card-actions">
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button className="btn" onClick={test} disabled={testing || !config?.base_url}>
          {testing ? "Testing…" : "Test connection"}
        </button>
      </div>
    </div>
  );
}

function TokenField({
  role,
  value,
  onChange,
  state,
  stateClass,
}: {
  role: RoleName;
  value: string;
  onChange: (v: string) => void;
  state: string;
  stateClass: string;
}) {
  return (
    <div className="token-field">
      <span className={`role-label ${role}`}>{role}</span>
      <input type="password" value={value} onChange={(e) => onChange(e.target.value)} placeholder="glsa_…" autoComplete="off" />
      <span className={`state ${stateClass}`}>{state}</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// LLM config section in the Settings drawer
// ─────────────────────────────────────────────────────────────────────────────

function LLMConfigSection() {
  const store = usePersistedStore();
  const llm = store.llm;
  const set = (patch: Partial<LLMConfig>) => store.setLLM(patch);

  const models = llm.provider === "anthropic" ? ANTHROPIC_MODELS : OPENAI_MODELS;
  const modelIncluded = models.includes(llm.model);

  const selectStyle: React.CSSProperties = {
    background: "var(--bg-2)",
    border: "1px solid var(--border-2)",
    borderRadius: 7,
    padding: "10px 13px",
    color: "var(--fg-0)",
    fontFamily: "var(--font-mono)",
    fontSize: 12.5,
  };

  return (
    <div>
      <h3 style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.09em", color: "var(--fg-2)", margin: "0 0 4px" }}>
        LLM
      </h3>
      <p className="muted" style={{ fontSize: 12, marginTop: 0, marginBottom: 18 }}>
        Pick an LLM provider and paste your API key. The key lives in your browser's localStorage and is sent
        directly to Anthropic/OpenAI — the Bifröst backend never sees it. Tool calls still route through Bifröst so
        role enforcement applies.
      </p>

      <div className="env-card">
        <div className="field-row">
          <div className="field">
            <label>Provider</label>
            <select
              value={llm.provider}
              onChange={(e) => {
                const provider = e.target.value as LLMProvider;
                const defaultModel = provider === "anthropic" ? ANTHROPIC_MODELS[0]! : OPENAI_MODELS[0]!;
                set({ provider, model: defaultModel });
              }}
              style={selectStyle}
            >
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="openai">OpenAI (GPT)</option>
            </select>
          </div>
          <div className="field">
            <label>Model</label>
            <select value={llm.model} onChange={(e) => set({ model: e.target.value })} style={selectStyle}>
              {!modelIncluded && <option value={llm.model}>{llm.model}</option>}
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="field">
          <label>API key</label>
          <input
            type="password"
            placeholder={llm.provider === "anthropic" ? "sk-ant-…" : "sk-proj-…"}
            value={llm.apiKey}
            onChange={(e) => set({ apiKey: e.target.value })}
            autoComplete="off"
          />
        </div>

        <div className="field">
          <label>System prompt</label>
          <textarea
            value={llm.systemPrompt}
            onChange={(e) => set({ systemPrompt: e.target.value })}
            rows={6}
            style={{
              background: "var(--bg-2)",
              border: "1px solid var(--border-2)",
              borderRadius: 7,
              padding: "10px 13px",
              color: "var(--fg-0)",
              fontFamily: "var(--font-mono)",
              fontSize: 11.5,
              lineHeight: 1.6,
              resize: "vertical",
            }}
          />
        </div>

        <div className="field-row">
          <div className="field">
            <label>Max tokens</label>
            <input
              type="number"
              value={llm.maxTokens}
              min={256}
              max={32768}
              onChange={(e) => set({ maxTokens: Number(e.target.value) })}
            />
          </div>
          <div className="field">
            <label>Temperature</label>
            <input
              type="number"
              value={llm.temperature}
              min={0}
              max={1}
              step={0.05}
              onChange={(e) => set({ temperature: Number(e.target.value) })}
            />
          </div>
        </div>

        <div style={{ marginTop: 4 }}>
          <span className={`badge ${llm.apiKey ? "ok" : "err"}`}>
            <span className="dot" />
            {llm.apiKey ? "key configured" : "no key"}
          </span>
        </div>
      </div>
    </div>
  );
}
