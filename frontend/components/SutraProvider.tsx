"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { getReplayStatus } from "@/lib/api";
import { useWebSocket, type WsStatus } from "@/lib/ws";
import type { AlertPushMessage, ReplayStatus } from "@/lib/types";

/** Custom window event dispatched after a successful replay reset. */
export const RESET_EVENT = "sutra:reset";

type AlertSubscriber = (msg: AlertPushMessage) => void;

interface SutraContextValue {
  /** Latest replay status (polled every 2s; 5s while backend is down). */
  status: ReplayStatus | null;
  /** True once the last status poll succeeded. */
  backendUp: boolean;
  /**
   * Current SIMULATED time as epoch ms (parsed from ReplayStatus.sim_time).
   * Alert timestamps live on the sim clock, so relative ages must be computed
   * against this, not wall time. Null while replay status is unavailable.
   */
  simNowMs: number | null;
  /** Connection state of the shared /ws/alerts socket. */
  alertsWsStatus: WsStatus;
  /** Subscribe to alert lifecycle pushes; returns an unsubscribe fn. */
  subscribeAlerts: (fn: AlertSubscriber) => () => void;
  /** Push a fresher status (e.g. from a replay-control POST response). */
  applyStatus: (s: ReplayStatus) => void;
}

const SutraContext = createContext<SutraContextValue | null>(null);

export function SutraProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<ReplayStatus | null>(null);
  const [backendUp, setBackendUp] = useState(false);
  const subscribers = useRef<Set<AlertSubscriber>>(new Set());

  // Poll GET /api/replay/status every 2s (backs off to 5s while down).
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      const s = await getReplayStatus();
      if (!alive) return;
      setStatus(s);
      setBackendUp(s !== null);
      timer = setTimeout(tick, s !== null ? 2000 : 5000);
    };
    void tick();
    return () => {
      alive = false;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);

  const onAlertMessage = useCallback((data: unknown) => {
    const msg = data as AlertPushMessage;
    if (
      msg &&
      (msg.kind === "alert_created" || msg.kind === "alert_updated") &&
      msg.alert
    ) {
      subscribers.current.forEach((fn) => {
        try {
          fn(msg);
        } catch {
          // a bad subscriber must never break the bus
        }
      });
    }
  }, []);

  // Shared alerts socket — only attempts to connect while the backend is up,
  // so a dead backend produces no connection churn or console noise.
  const alertsWsStatus = useWebSocket("/ws/alerts", onAlertMessage, backendUp);

  const subscribeAlerts = useCallback((fn: AlertSubscriber) => {
    subscribers.current.add(fn);
    return () => {
      subscribers.current.delete(fn);
    };
  }, []);

  const applyStatus = useCallback((s: ReplayStatus) => {
    setStatus(s);
    setBackendUp(true);
  }, []);

  let simNowMs: number | null = null;
  if (status !== null) {
    const parsed = Date.parse(status.sim_time);
    if (Number.isFinite(parsed)) simNowMs = parsed;
  }

  return (
    <SutraContext.Provider
      value={{
        status,
        backendUp,
        simNowMs,
        alertsWsStatus,
        subscribeAlerts,
        applyStatus,
      }}
    >
      {children}
    </SutraContext.Provider>
  );
}

export function useSutra(): SutraContextValue {
  const ctx = useContext(SutraContext);
  if (!ctx) throw new Error("useSutra must be used inside <SutraProvider>");
  return ctx;
}
