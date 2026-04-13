// Tiny localStorage-backed store for UI preferences:
// - list of known MCP servers (URL + label)
// - currently selected server
// Plain pattern, no Zustand dependency — keeps the footprint minimal.

import { useEffect, useState } from "react";

export interface MCPServerEntry {
  id: string;
  label: string;
  url: string;
}

const KEY = "bifrost-ui-v1";

interface Persisted {
  servers: MCPServerEntry[];
  activeServerId: string;
}

const DEFAULTS: Persisted = {
  servers: [{ id: "local", label: "Local (Docker)", url: "http://127.0.0.1:8765" }],
  activeServerId: "local",
};

function load(): Persisted {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Persisted;
    if (!parsed.servers || parsed.servers.length === 0) return DEFAULTS;
    return parsed;
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
    servers: state.servers,
    activeServerId: state.activeServerId,
    activeServer: state.servers.find((s) => s.id === state.activeServerId) ?? state.servers[0]!,
    setActiveServer: (id: string) => {
      state = { ...state, activeServerId: id };
      emit();
    },
    addServer: (label: string, url: string) => {
      const id = `srv-${Date.now()}`;
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
  };
}
