// Bifröst REST bridge client.
// `baseUrl` is runtime-configurable so the UI can point at different MCP servers.

type Envelope<T> = { ok: true; data: T } | { ok: false; error: string; message: string };

async function call<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const env: Envelope<T> = await r.json();
  if (!env.ok) throw new Error(`${env.error}: ${env.message}`);
  return env.data;
}

export type EnvName = "dev" | "perf" | "prod";
export type RoleName = "viewer" | "editor" | "admin";

export interface EnvironmentDescriptor {
  base_url: string;
  tls_verify: boolean;
  timeout_seconds: number;
  rate_limit_rps: number;
  has_viewer: boolean;
  has_editor: boolean;
  has_admin: boolean;
}

export interface ServerInfo {
  version: string;
  active_environment: EnvName;
  active_role: RoleName;
  transport: { mode: string; host: string; port: number; path_prefix: string };
  environments: Record<EnvName, EnvironmentDescriptor>;
}

export interface HealthStatus {
  database: string;
  version: string;
  commit: string;
  enterprise: boolean;
}

export interface DashboardSummary {
  uid: string;
  title: string;
  folder_title?: string | null;
  folder_uid?: string | null;
  tags?: string[];
  url?: string;
}

export interface Datasource {
  uid?: string;
  name: string;
  type: string;
  url?: string;
  is_default?: boolean;
}

export interface Folder {
  uid: string;
  title: string;
}

export interface RoleTestResult {
  status: "ok" | "error" | "missing";
  latency_ms: number | null;
  error: string | null;
}

export interface EnvTestResult {
  environment: EnvName;
  base_url: string;
  roles: Record<RoleName, RoleTestResult>;
}

export interface EnvUpdate {
  base_url?: string;
  tls_verify?: boolean;
  timeout_seconds?: number;
  rate_limit_rps?: number;
  service_accounts?: Partial<Record<RoleName, string>>;
}

export function makeClient(baseUrl: string) {
  const url = baseUrl.replace(/\/$/, "");
  return {
    baseUrl: url,
    serverInfo: () => call<ServerInfo>(url, "/api/server-info"),
    health: () => call<HealthStatus>(url, "/api/health"),
    dashboards: (limit = 500) => call<DashboardSummary[]>(url, `/api/dashboards?limit=${limit}`),
    datasources: () => call<Datasource[]>(url, "/api/datasources"),
    folders: () => call<Folder[]>(url, "/api/folders"),
    updateEnv: (name: EnvName, patch: EnvUpdate) =>
      call<{ environment: string; evicted: number; config: EnvironmentDescriptor }>(url, `/api/environments/${name}`, {
        method: "PUT",
        body: JSON.stringify(patch),
      }),
    testEnv: (name: EnvName) =>
      call<EnvTestResult>(url, `/api/environments/${name}/test`, { method: "POST" }),
    setActive: (patch: { environment?: EnvName; role?: RoleName }) =>
      call<{ active_environment: EnvName; active_role: RoleName }>(url, "/api/active", {
        method: "POST",
        body: JSON.stringify(patch),
      }),
  };
}

export type BifrostClient = ReturnType<typeof makeClient>;
