"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { RESET_EVENT, useSutra } from "@/components/SutraProvider";
import { Panel, SeverityDot, StatusPill, severityColor } from "@/components/ui";
import { getAlerts } from "@/lib/api";
import { relativeAge } from "@/lib/format";
import type { AlertStatus, AlertSummary, Severity } from "@/lib/types";

const STATUS_FILTERS: Array<AlertStatus | "all"> = [
  "all",
  "open",
  "held",
  "stepup",
  "dismissed",
];
const SEVERITY_FILTERS: Array<Severity | "all"> = [
  "all",
  "critical",
  "high",
  "medium",
];

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 font-mono text-xs transition-colors ${
        active
          ? "border-accent/60 bg-accent/15 text-accent"
          : "border-edge text-muted hover:border-muted hover:text-body"
      }`}
    >
      {children}
    </button>
  );
}

export default function AlertsPage() {
  const router = useRouter();
  const { backendUp, subscribeAlerts } = useSutra();
  const [alerts, setAlerts] = useState<AlertSummary[] | null>(null);
  const [statusFilter, setStatusFilter] = useState<AlertStatus | "all">("all");
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set());
  const knownIds = useRef<Set<string> | null>(null);
  const flashTimers = useRef<Array<ReturnType<typeof setTimeout>>>([]);

  const refetch = async () => {
    const res = await getAlerts();
    if (!res) return;
    const list = res.alerts;
    // Flash rows that are new since the previous fetch (skip the first load).
    if (knownIds.current !== null) {
      const fresh = list
        .filter((a) => !knownIds.current!.has(a.alert_id))
        .map((a) => a.alert_id);
      if (fresh.length > 0) {
        setFlashIds((prev) => new Set([...Array.from(prev), ...fresh]));
        const t = setTimeout(() => {
          setFlashIds((prev) => {
            const next = new Set(prev);
            fresh.forEach((id) => next.delete(id));
            return next;
          });
        }, 1100);
        flashTimers.current.push(t);
      }
    }
    knownIds.current = new Set(list.map((a) => a.alert_id));
    setAlerts(list);
  };

  // Poll every 5s + refetch (debounced) on every WS alert push.
  useEffect(() => {
    let alive = true;
    const safeRefetch = () => {
      if (alive) void refetch();
    };
    safeRefetch();
    const interval = setInterval(safeRefetch, 5000);

    let debounce: ReturnType<typeof setTimeout> | undefined;
    const unsub = subscribeAlerts(() => {
      if (debounce !== undefined) clearTimeout(debounce);
      debounce = setTimeout(safeRefetch, 250);
    });

    const timers = flashTimers.current;
    const clear = () => {
      knownIds.current = null;
      setAlerts(null);
      setFlashIds(new Set());
    };
    window.addEventListener(RESET_EVENT, clear);

    return () => {
      alive = false;
      clearInterval(interval);
      if (debounce !== undefined) clearTimeout(debounce);
      unsub();
      timers.forEach(clearTimeout);
      window.removeEventListener(RESET_EVENT, clear);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscribeAlerts]);

  const visible = (alerts ?? [])
    .filter((a) => statusFilter === "all" || a.status === statusFilter)
    .filter((a) => severityFilter === "all" || a.severity === severityFilter)
    .sort(
      (a, b) => b.risk - a.risk || b.updated_ts.localeCompare(a.updated_ts),
    );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <h1 className="text-lg font-semibold tracking-wide">Alert queue</h1>
        <div className="flex items-center gap-1.5">
          <span className="mr-1 text-[11px] uppercase tracking-wider text-muted">
            status
          </span>
          {STATUS_FILTERS.map((s) => (
            <Chip
              key={s}
              active={statusFilter === s}
              onClick={() => setStatusFilter(s)}
            >
              {s}
            </Chip>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="mr-1 text-[11px] uppercase tracking-wider text-muted">
            severity
          </span>
          {SEVERITY_FILTERS.map((s) => (
            <Chip
              key={s}
              active={severityFilter === s}
              onClick={() => setSeverityFilter(s)}
            >
              {s}
            </Chip>
          ))}
        </div>
      </div>

      <Panel>
        {alerts === null ? (
          <div className="flex min-h-[200px] items-center justify-center text-sm text-muted">
            {backendUp ? "loading alerts…" : "waiting for backend…"}
          </div>
        ) : visible.length === 0 ? (
          <div className="flex min-h-[200px] items-center justify-center text-sm text-muted">
            no alerts match the current filters
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-edge text-[11px] uppercase tracking-wider text-muted">
                  <th className="px-4 py-2.5 font-medium">Sev</th>
                  <th className="px-2 py-2.5 font-medium">Risk</th>
                  <th className="px-2 py-2.5 font-medium">Title</th>
                  <th className="px-2 py-2.5 font-medium">Entity</th>
                  <th className="px-2 py-2.5 font-medium">Age</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge/60">
                {visible.map((a) => (
                  <tr
                    key={a.alert_id}
                    onClick={() => router.push(`/alerts/${a.alert_id}`)}
                    className={`cursor-pointer transition-colors hover:bg-edge/40 ${
                      flashIds.has(a.alert_id) ? "flash-row" : ""
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <SeverityDot severity={a.severity} />
                    </td>
                    <td
                      className="px-2 py-2.5 font-mono text-base font-bold tabular-nums"
                      style={{ color: severityColor(a.severity) }}
                    >
                      {a.risk}
                    </td>
                    <td className="max-w-[560px] px-2 py-2.5">
                      <span className="block truncate text-body" title={a.title}>
                        {a.title}
                      </span>
                      <span className="font-mono text-[11px] text-muted">
                        {a.alert_id} · {a.evidence_count} evidence
                        {a.tags.includes("quantum") ? " · quantum" : ""}
                      </span>
                    </td>
                    <td className="px-2 py-2.5 font-mono text-xs text-body/80">
                      <span className="text-muted">{a.entity_type}</span>{" "}
                      {a.entity_id}
                    </td>
                    <td className="px-2 py-2.5 font-mono text-xs text-muted">
                      {relativeAge(a.created_ts)}
                    </td>
                    <td className="px-4 py-2.5">
                      <StatusPill status={a.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
