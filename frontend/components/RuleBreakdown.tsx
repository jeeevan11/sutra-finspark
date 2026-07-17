"use client";

import type { RuleHit } from "@/lib/types";

const DOMAIN_COLOR: Record<RuleHit["domain"], string> = {
  security: "#F59E0B",
  transaction: "#22D3EE",
  fused: "#EF4444",
  quantum: "#34D399",
};

const ML_COLOR = "#94A3B8";

/**
 * Horizontal stacked bar of per-rule point contributions, plus the ML anomaly
 * score shown as its own (visually distinct, hatched-gray) segment and row.
 */
export function RuleBreakdown({
  ruleHits,
  mlScore,
}: {
  ruleHits: RuleHit[];
  mlScore: number;
}) {
  const rulesTotal = ruleHits.reduce((acc, r) => acc + r.points, 0);
  const total = rulesTotal + mlScore;

  if (total <= 0) {
    return (
      <div className="py-4 text-center text-sm text-muted">
        no rule hits recorded
      </div>
    );
  }

  return (
    <div>
      {/* stacked contribution bar (2px gaps between segments) */}
      <div className="flex h-5 w-full gap-[2px] overflow-hidden rounded">
        {ruleHits.map((r) => (
          <div
            key={`${r.rule_id}-${r.ts}`}
            className="h-full min-w-[3px] rounded-[2px]"
            style={{
              width: `${(r.points / total) * 100}%`,
              backgroundColor: DOMAIN_COLOR[r.domain] ?? "#8B9BB4",
            }}
            title={`${r.rule_id} ${r.name}: +${r.points}`}
          />
        ))}
        {mlScore > 0 && (
          <div
            className="h-full min-w-[3px] rounded-[2px] opacity-80"
            style={{
              width: `${(mlScore / total) * 100}%`,
              backgroundImage: `repeating-linear-gradient(45deg, ${ML_COLOR}, ${ML_COLOR} 3px, transparent 3px, transparent 6px)`,
              backgroundColor: "rgba(148,163,184,0.25)",
            }}
            title={`ML anomaly: +${mlScore}/40`}
          />
        )}
      </div>

      {/* per-rule rows */}
      <ul className="mt-3 space-y-1.5">
        {ruleHits.map((r) => (
          <li
            key={`${r.rule_id}-${r.ts}-row`}
            className="flex items-baseline gap-2.5 text-[13px]"
          >
            <span
              className="mt-0.5 h-2.5 w-2.5 shrink-0 self-center rounded-sm"
              style={{ backgroundColor: DOMAIN_COLOR[r.domain] ?? "#8B9BB4" }}
            />
            <span className="w-9 shrink-0 font-mono text-xs font-bold text-body">
              {r.rule_id}
            </span>
            <span className="shrink-0 font-medium text-body/90">{r.name}</span>
            <span className="truncate text-xs text-muted" title={r.detail}>
              {r.detail}
            </span>
            <span className="ml-auto shrink-0 font-mono text-sm font-bold tabular-nums text-body">
              +{r.points}
            </span>
          </li>
        ))}
        <li className="flex items-baseline gap-2.5 border-t border-edge pt-1.5 text-[13px]">
          <span
            className="mt-0.5 h-2.5 w-2.5 shrink-0 self-center rounded-sm opacity-80"
            style={{
              backgroundImage: `repeating-linear-gradient(45deg, ${ML_COLOR}, ${ML_COLOR} 2px, transparent 2px, transparent 4px)`,
              backgroundColor: "rgba(148,163,184,0.25)",
            }}
          />
          <span className="font-medium text-body/90">ML anomaly</span>
          <span className="text-xs text-muted">
            IsolationForest anomaly contribution
          </span>
          <span className="ml-auto shrink-0 font-mono text-sm font-bold tabular-nums text-body">
            +{mlScore}
            <span className="font-normal text-muted">/40</span>
          </span>
        </li>
      </ul>
    </div>
  );
}
