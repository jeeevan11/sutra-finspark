"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Panel } from "@/components/ui";
import { getMetrics } from "@/lib/api";
import {
  formatINR,
  formatIndianNumber,
  formatISTFull,
  formatPct01,
  formatSeconds,
} from "@/lib/format";
import type { Metrics, ModeStats } from "@/lib/types";

// Chart identity colors, CVD-validated against the panel surface:
// siloed (before) = deep amber, fused (after) = deep cyan.
const SILOED_COLOR = "#D97706";
const FUSED_COLOR = "#0EA5C6";

const TOOLTIP_STYLE: React.CSSProperties = {
  backgroundColor: "#080D18",
  border: "1px solid #24344E",
  borderRadius: 6,
  fontSize: 12,
  fontFamily: "var(--font-jetbrains), monospace",
  color: "#E2E8F0",
};

function barColor(mode: string): string {
  return mode === "Siloed" ? SILOED_COLOR : FUSED_COLOR;
}

function ModeBarChart({
  title,
  data,
}: {
  title: string;
  data: Array<{ mode: string; value: number }>;
}) {
  // Guard: never hand Recharts an empty series (the parent only renders this
  // when metrics are ready, but keep it defensive).
  if (data.length === 0) {
    return (
      <Panel title={title} className="px-3 py-3">
        <div className="flex h-[186px] items-center justify-center text-sm text-muted">
          no data
        </div>
      </Panel>
    );
  }
  return (
    <Panel title={title} className="px-3 py-3">
      {/* Fixed-px height parent so ResponsiveContainer never collapses to 0. */}
      <div className="h-[186px] w-full pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 24, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid
              vertical={false}
              stroke="#24344E"
              strokeDasharray="0"
            />
            <XAxis
              dataKey="mode"
              tick={{ fill: "#94A3B8", fontSize: 13 }}
              axisLine={{ stroke: "#24344E" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "#8B9BB4", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            <Tooltip
              cursor={{ fill: "rgba(30,41,59,0.4)" }}
              contentStyle={TOOLTIP_STYLE}
              formatter={(v) => [formatIndianNumber(Number(v)), "count"]}
            />
            {/*
              dataKey "value" matches the data objects; literal hex fills (never
              CSS vars — Recharts writes fill straight to the SVG attribute and
              can't resolve var(--x)). isAnimationActive is off so bars paint at
              full height immediately even though metrics arrive async after
              mount (the enter-animation could otherwise leave them at height 0).
            */}
            <Bar
              dataKey="value"
              barSize={56}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
              fill={FUSED_COLOR}
            >
              {data.map((d) => (
                <Cell key={d.mode} fill={barColor(d.mode)} />
              ))}
              <LabelList
                dataKey="value"
                position="top"
                formatter={(v: number) => formatIndianNumber(v)}
                fill="#E2E8F0"
                fontSize={13}
                fontFamily="var(--font-jetbrains), monospace"
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function ModeStatsCard({
  label,
  stats,
  color,
}: {
  label: string;
  stats: ModeStats;
  color: string;
}) {
  return (
    <Panel className="px-5 py-4">
      <div className="flex items-center gap-2">
        <span
          className="h-2.5 w-2.5 rounded-sm"
          style={{ backgroundColor: color }}
        />
        <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
          {label}
        </h3>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 font-mono text-sm">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted">
            precision
          </div>
          <div className="text-xl font-bold tabular-nums">
            {formatPct01(stats.precision)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted">
            recall
          </div>
          <div className="text-xl font-bold tabular-nums">
            {formatPct01(stats.recall)}
          </div>
        </div>
        <div className="text-xs text-muted">
          TP <span className="text-ok">{stats.true_positives}</span> · FP{" "}
          <span className="text-critical">{stats.false_positives}</span>
        </div>
        <div className="text-xs text-muted">
          scenarios{" "}
          <span className="text-body">
            {stats.detected_scenarios.length > 0
              ? stats.detected_scenarios.join(", ")
              : "none"}
          </span>
        </div>
      </div>
    </Panel>
  );
}

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "empty">("loading");

  const load = useCallback(async () => {
    setState("loading");
    const m = await getMetrics();
    if (m) {
      setMetrics(m);
      setState("ready");
    } else {
      setMetrics(null);
      setState("empty");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-3 xl:-mb-40 xl:h-[calc(100dvh-92px)] xl:overflow-hidden">
      <div className="flex shrink-0 items-center gap-4">
        <h1 className="text-lg font-semibold tracking-wide">
          Benchmark metrics — siloed vs SUTRA fused
        </h1>
        <button
          onClick={() => void load()}
          disabled={state === "loading"}
          className="rounded border border-accent/60 px-3 py-1 font-mono text-xs text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
        >
          {state === "loading" ? "Refreshing…" : "Refresh"}
        </button>
        {metrics && (
          <span className="ml-auto font-mono text-xs text-muted">
            seed {metrics.seed} · {metrics.duration_hours}h window · generated{" "}
            {formatISTFull(metrics.generated_ts)} IST
          </span>
        )}
      </div>

      {state !== "ready" || !metrics ? (
        <Panel>
          <div className="flex min-h-[260px] flex-col items-center justify-center gap-2 text-sm text-muted">
            {state === "loading" ? (
              "loading metrics…"
            ) : (
              <>
                <p>No benchmark metrics available.</p>
                <p>
                  Run{" "}
                  <code className="rounded border border-edge bg-night px-1.5 py-0.5 font-mono text-accent">
                    make bench
                  </code>{" "}
                  to generate benchmark metrics.
                </p>
              </>
            )}
          </div>
        </Panel>
      ) : (
        <>
          {/* Before / after hero */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <Panel className="px-5 py-4">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
                Siloed alerts
              </div>
              <div
                className="mt-1 font-mono text-4xl font-bold tabular-nums"
                style={{ color: SILOED_COLOR }}
              >
                {formatIndianNumber(metrics.modes.siloed.total_alerts)}
              </div>
              <div className="mt-1 text-xs text-muted">
                independent SIEM + FRM alerting, {metrics.duration_hours}h
              </div>
            </Panel>
            <Panel className="px-5 py-4">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
                SUTRA fused
              </div>
              <div
                className="mt-1 font-mono text-4xl font-bold tabular-nums"
                style={{ color: FUSED_COLOR }}
              >
                {formatIndianNumber(metrics.modes.fused.total_alerts)}
              </div>
              <div className="mt-1 text-xs text-muted">
                entity-fused incidents, same telemetry
              </div>
            </Panel>
            <Panel className="border-ok/40 px-5 py-4">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
                Alert volume
              </div>
              <div className="mt-1 font-mono text-4xl font-bold tabular-nums text-ok">
                −{metrics.summary.alert_reduction_pct.toFixed(1)}%
              </div>
              <div className="mt-1 text-xs text-muted">
                fewer alerts for analysts to triage
              </div>
            </Panel>
          </div>

          {/* Precision / recall per mode */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <ModeStatsCard
              label="Siloed mode"
              stats={metrics.modes.siloed}
              color={SILOED_COLOR}
            />
            <ModeStatsCard
              label="Fused mode"
              stats={metrics.modes.fused}
              color={FUSED_COLOR}
            />
          </div>

          {/* Per-scenario table */}
          <Panel title="Attack scenarios">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-edge text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-2 font-medium">Scenario</th>
                    <th className="px-2 py-2 font-medium">Name</th>
                    <th className="px-2 py-2 font-medium">SUTRA fused</th>
                    <th className="px-4 py-2 font-medium">Siloed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge/60">
                  {(["A", "B", "C"] as const)
                    .filter((k) => metrics.scenarios[k])
                    .map((k) => {
                      const sc = metrics.scenarios[k];
                      return (
                        <tr key={k}>
                          <td className="px-4 py-2 font-mono text-base font-bold text-accent">
                            {k}
                          </td>
                          <td className="px-2 py-2 text-body">{sc.name}</td>
                          <td className="px-2 py-2 font-mono text-xs">
                            {sc.fused.detected ? (
                              <span className="text-ok">
                                ✓ detected · risk {sc.fused.risk} ·{" "}
                                {formatSeconds(sc.fused.time_to_detect_s)} to
                                detect
                              </span>
                            ) : (
                              <span className="text-critical">✗ missed</span>
                            )}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs">
                            <span
                              className={
                                sc.siloed.detected ? "text-ok" : "text-critical"
                              }
                            >
                              {sc.siloed.detected ? "✓ detected" : "✗ missed"}
                            </span>{" "}
                            <span className="text-muted">
                              · max score {sc.siloed.max_score} ·{" "}
                              {sc.siloed.alerts} alerts — {sc.siloed.note}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* FP comparison + business summary */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
            <Panel className="px-5 py-4">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
                False positives
              </div>
              <div className="mt-2 font-mono text-sm">
                <span style={{ color: SILOED_COLOR }}>
                  siloed {formatIndianNumber(metrics.modes.siloed.false_positives)}
                </span>
                <span className="text-muted"> → </span>
                <span style={{ color: FUSED_COLOR }}>
                  fused {formatIndianNumber(metrics.modes.fused.false_positives)}
                </span>
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-ok">
                −{metrics.summary.fp_reduction_pct.toFixed(1)}%
              </div>
            </Panel>
            <Panel className="px-5 py-4">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
                Analyst hours saved / day
              </div>
              <div className="mt-2 font-mono text-3xl font-bold tabular-nums text-body">
                {metrics.summary.analyst_hours_saved_per_day.toFixed(1)}h
              </div>
            </Panel>
            <Panel className="col-span-1 px-5 py-4 lg:col-span-2">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
                Rupees at risk flagged
              </div>
              <div className="mt-2 font-mono text-3xl font-bold tabular-nums text-body">
                {formatINR(metrics.summary.rupees_at_risk_flagged)}
              </div>
              <div className="mt-1 text-xs text-muted">
                scenario transaction value caught by fused detection
              </div>
            </Panel>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <ModeBarChart
              title="Alert volume by mode"
              data={[
                { mode: "Siloed", value: metrics.modes.siloed.total_alerts },
                { mode: "Fused", value: metrics.modes.fused.total_alerts },
              ]}
            />
            <ModeBarChart
              title="False positives by mode"
              data={[
                {
                  mode: "Siloed",
                  value: metrics.modes.siloed.false_positives,
                },
                { mode: "Fused", value: metrics.modes.fused.false_positives },
              ]}
            />
          </div>
        </>
      )}
    </div>
  );
}
