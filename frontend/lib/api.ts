import type {
  ActionResponse,
  ActionType,
  AlertDetail,
  AlertsResponse,
  GraphResponse,
  Metrics,
  QuantumResponse,
  ReplayControlResponse,
  ReplaySpeed,
  ReplayStatus,
  Scenario,
  VerifyResponse,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export const WS_BASE = API_BASE.replace(/^http/, "ws");

/**
 * Fetch JSON, returning null on ANY failure (network down, non-2xx, bad JSON).
 * Never throws — the UI must degrade gracefully when the backend is not up.
 */
async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

async function postJSON<T>(path: string, body?: unknown): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: body !== undefined ? { "Content-Type": "application/json" } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

// --- Alerts ---

export function getAlerts(filters?: {
  status?: string;
  severity?: string;
}): Promise<AlertsResponse | null> {
  const qs = new URLSearchParams();
  if (filters?.status) qs.set("status", filters.status);
  if (filters?.severity) qs.set("severity", filters.severity);
  const q = qs.toString();
  return getJSON<AlertsResponse>(`/api/alerts${q ? `?${q}` : ""}`);
}

export function getAlert(alertId: string): Promise<AlertDetail | null> {
  return getJSON<AlertDetail>(`/api/alerts/${encodeURIComponent(alertId)}`);
}

export function postAlertAction(
  alertId: string,
  action: ActionType,
): Promise<ActionResponse | null> {
  return postJSON<ActionResponse>(
    `/api/alerts/${encodeURIComponent(alertId)}/action`,
    { action },
  );
}

export function verifyAlert(alertId: string): Promise<VerifyResponse | null> {
  return getJSON<VerifyResponse>(
    `/api/alerts/${encodeURIComponent(alertId)}/verify`,
  );
}

// --- Metrics / Quantum ---

export function getMetrics(): Promise<Metrics | null> {
  return getJSON<Metrics>("/api/metrics");
}

export function getQuantum(): Promise<QuantumResponse | null> {
  return getJSON<QuantumResponse>("/api/quantum");
}

// --- Replay control ---

export function getReplayStatus(): Promise<ReplayStatus | null> {
  return getJSON<ReplayStatus>("/api/replay/status");
}

export function replayStart(
  speed: ReplaySpeed,
): Promise<ReplayControlResponse | null> {
  return postJSON<ReplayControlResponse>("/api/replay/start", { speed });
}

export function replayPause(): Promise<ReplayControlResponse | null> {
  return postJSON<ReplayControlResponse>("/api/replay/pause");
}

export function replayReset(): Promise<ReplayControlResponse | null> {
  return postJSON<ReplayControlResponse>("/api/replay/reset");
}

export function replayInject(
  scenario: Scenario,
): Promise<ReplayControlResponse | null> {
  return postJSON<ReplayControlResponse>(`/api/replay/inject/${scenario}`);
}

export function getGraph(entityId: string): Promise<GraphResponse | null> {
  return getJSON<GraphResponse>(`/api/graph/${encodeURIComponent(entityId)}`);
}
