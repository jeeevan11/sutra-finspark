"use client";

import Link from "next/link";
import { formatIST } from "@/lib/format";
import type { AlertSummary } from "@/lib/types";
import { Panel, SeverityDot, severityColor } from "./ui";

export interface FeedItem {
  alert: AlertSummary;
  /** true when the row arrived over the live WS (drives the flash animation) */
  fresh: boolean;
}

/** Mini alert feed for Live Ops — newest first, clicking opens the detail. */
export function AlertFeed({
  items,
  waiting,
}: {
  items: FeedItem[];
  waiting: boolean;
}) {
  return (
    <Panel title="Alerts" className="flex min-h-0 flex-col">
      <div className="river-scroll min-h-0 flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <div className="flex h-full min-h-[120px] items-center justify-center px-4 text-center text-sm text-muted">
            {waiting ? "waiting for backend…" : "no alerts yet"}
          </div>
        ) : (
          <ul className="divide-y divide-edge/50">
            {items.map(({ alert, fresh }) => (
              <li key={alert.alert_id} className={fresh ? "flash-row" : ""}>
                <Link
                  href={`/alerts/${alert.alert_id}`}
                  className="block px-3 py-2.5 transition-colors hover:bg-edge/40"
                >
                  <div className="flex items-center gap-2">
                    <SeverityDot severity={alert.severity} />
                    <span
                      className="font-mono text-sm font-bold tabular-nums"
                      style={{ color: severityColor(alert.severity) }}
                    >
                      {alert.risk}
                    </span>
                    <span className="ml-auto font-mono text-[10px] text-muted">
                      {formatIST(alert.created_ts)}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-body/90">
                    {alert.title}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-muted">
                    {alert.alert_id} · {alert.entity_id}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
