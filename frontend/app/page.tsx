"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertFeed, type FeedItem } from "@/components/AlertFeed";
import { EventRiver } from "@/components/EventRiver";
import { RESET_EVENT, useSutra } from "@/components/SutraProvider";
import { getAlerts } from "@/lib/api";
import { formatIndianNumber } from "@/lib/format";
import { useWebSocket } from "@/lib/ws";
import type { AlertPushMessage, EventMessage } from "@/lib/types";

const RIVER_CAP = 100;
const FEED_CAP = 50;

function Kpi({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-edge bg-panel px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
        {label}
      </div>
      <div className="mt-1 font-mono text-2xl font-bold tabular-nums">
        {children}
      </div>
    </div>
  );
}

export default function LiveOpsPage() {
  const { status, backendUp, subscribeAlerts } = useSutra();
  const [security, setSecurity] = useState<EventMessage[]>([]);
  const [transactions, setTransactions] = useState<EventMessage[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);

  // Route /ws/events messages into the two rivers by `stream`.
  const onEvent = useCallback((data: unknown) => {
    const m = data as EventMessage;
    if (!m || m.kind !== "event" || !m.event_id) return;
    if (m.stream === "transaction") {
      setTransactions((prev) => [m, ...prev].slice(0, RIVER_CAP));
    } else {
      setSecurity((prev) => [m, ...prev].slice(0, RIVER_CAP));
    }
  }, []);
  useWebSocket("/ws/events", onEvent, backendUp);

  // Mini alert feed: seed once from GET /api/alerts, then live via /ws/alerts.
  useEffect(() => {
    let alive = true;
    void getAlerts().then((res) => {
      if (!alive || !res) return;
      const seeded = [...res.alerts]
        .sort((a, b) => b.created_ts.localeCompare(a.created_ts))
        .slice(0, FEED_CAP)
        .map((alert) => ({ alert, fresh: false }));
      setFeed((prev) => (prev.length > 0 ? prev : seeded));
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(
    () =>
      subscribeAlerts((msg: AlertPushMessage) => {
        setFeed((prev) => {
          if (msg.kind === "alert_created") {
            const rest = prev.filter(
              (f) => f.alert.alert_id !== msg.alert.alert_id,
            );
            return [{ alert: msg.alert, fresh: true }, ...rest].slice(
              0,
              FEED_CAP,
            );
          }
          // alert_updated → refresh in place, keep position, no flash
          return prev.map((f) =>
            f.alert.alert_id === msg.alert.alert_id
              ? { alert: msg.alert, fresh: f.fresh }
              : f,
          );
        });
      }),
    [subscribeAlerts],
  );

  // Demo-dock reset broadcast → clear all client-side buffers.
  useEffect(() => {
    const clear = () => {
      setSecurity([]);
      setTransactions([]);
      setFeed([]);
    };
    window.addEventListener(RESET_EVENT, clear);
    return () => window.removeEventListener(RESET_EVENT, clear);
  }, []);

  const openAlerts = status?.open_alerts;

  return (
    <div className="flex flex-col gap-4">
      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Events / min">
          {backendUp && status ? (
            <span className="text-body">
              {formatIndianNumber(Math.round(status.events_per_min))}
            </span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </Kpi>
        <Kpi label="Open alerts (C / H / M)">
          {backendUp && openAlerts ? (
            <span className="flex items-baseline gap-3">
              <span className="text-critical">{openAlerts.critical}</span>
              <span className="text-high">{openAlerts.high}</span>
              <span className="text-medium">{openAlerts.medium}</span>
            </span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </Kpi>
        <Kpi label="Held transactions">
          {backendUp && status ? (
            <span className={status.held_txns > 0 ? "text-critical" : "text-body"}>
              {formatIndianNumber(status.held_txns)}
            </span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </Kpi>
        <Kpi label="HNDL-flagged assets">
          {backendUp && status ? (
            <span className={status.hndl_assets > 0 ? "text-high" : "text-body"}>
              {formatIndianNumber(status.hndl_assets)}
            </span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </Kpi>
      </div>

      {/* Rivers + mini alert feed */}
      <div className="grid h-[calc(100vh-15.5rem)] min-h-[420px] grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr_340px]">
        <EventRiver title="Security" events={security} waiting={!backendUp} />
        <EventRiver
          title="Transactions"
          events={transactions}
          waiting={!backendUp}
        />
        <AlertFeed items={feed} waiting={!backendUp} />
      </div>
    </div>
  );
}
