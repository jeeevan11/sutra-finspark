"use client";

import { formatIST } from "@/lib/format";
import type { EvidenceItem } from "@/lib/types";
import { TypeBadge } from "./ui";

/**
 * Vertical evidence chain: timeline of EvidenceItem cards connected by a
 * subtle line. Action records (type === "action") get a cyan border.
 * Cards are keyed by event_id, so items that arrive during live polling
 * mount fresh and pick up the row-flash animation.
 */
export function EvidenceTimeline({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) {
    return (
      <div className="py-6 text-center text-sm text-muted">
        no evidence recorded yet
      </div>
    );
  }
  return (
    <ol className="relative ml-2 space-y-3 border-l border-edge pl-5">
      {evidence.map((item) => {
        const isAction = item.type === "action";
        return (
          <li key={item.event_id} className="relative">
            {/* node on the connecting line */}
            <span
              className={`absolute -left-[26.5px] top-3 h-2 w-2 rounded-full border-2 ${
                isAction
                  ? "border-accent bg-accent"
                  : "border-muted bg-panel"
              }`}
            />
            <div
              className={`flash-row rounded-md border bg-panel px-3.5 py-2.5 ${
                isAction ? "border-accent/70" : "border-edge"
              }`}
            >
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="font-mono text-xs tabular-nums text-muted">
                  {formatIST(item.ts)}
                </span>
                <TypeBadge type={item.type} />
                <span className="font-mono text-[10px] text-muted/80">
                  {item.event_id}
                </span>
                {item.rule_ids.length > 0 && (
                  <span className="ml-auto flex flex-wrap gap-1">
                    {item.rule_ids.map((r) => (
                      <span
                        key={r}
                        className="rounded border border-edge bg-night px-1.5 py-px font-mono text-[10px] text-accent/90"
                      >
                        {r}
                      </span>
                    ))}
                  </span>
                )}
              </div>
              <p
                className={`mt-1.5 font-mono text-[13px] leading-snug ${
                  isAction ? "text-accent" : "text-body/90"
                }`}
              >
                {item.summary}
              </p>
              {item.entity_refs.length > 0 && (
                <p className="mt-1 font-mono text-[10px] text-muted">
                  {item.entity_refs.join(" · ")}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
