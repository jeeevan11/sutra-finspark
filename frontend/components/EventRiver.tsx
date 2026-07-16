"use client";

import { formatIST } from "@/lib/format";
import type { EventMessage } from "@/lib/types";
import { Panel, TypeBadge } from "./ui";

/**
 * One live event river (Security or Transactions).
 * Newest on top, capped upstream at 100 rows. Rows are keyed by event_id and
 * mount exactly once, so the `flash-row` animation fires only on arrival.
 */
export function EventRiver({
  title,
  events,
  waiting,
}: {
  title: string;
  events: EventMessage[];
  waiting: boolean;
}) {
  return (
    <Panel
      title={title}
      right={
        <span className="font-mono text-[11px] text-muted">
          {events.length > 0 ? `${events.length} rows` : ""}
        </span>
      }
      className="flex min-h-0 flex-col"
    >
      <div className="river-scroll min-h-0 flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <div className="flex h-full min-h-[120px] items-center justify-center text-sm text-muted">
            {waiting ? "waiting for backend…" : "no events yet — start the replay"}
          </div>
        ) : (
          <ul className="divide-y divide-edge/50">
            {events.map((e) => (
              <li
                key={e.event_id}
                className="flash-row flex items-center gap-2.5 px-3 py-[5px] font-mono text-[12.5px] leading-snug"
              >
                <span className="shrink-0 tabular-nums text-muted">
                  {formatIST(e.ts)}
                </span>
                <TypeBadge type={e.type} />
                <span className="truncate text-body/90" title={e.summary}>
                  {e.summary}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
