"use client";

import { useEffect, useMemo, useState } from "react";
import { getGraph } from "@/lib/api";
import type { GraphResponse } from "@/lib/types";

/**
 * 1-hop entity neighborhood as a deterministic radial SVG — the correlation
 * primitive made visible. Hand-rolled (no graph library): the payload is small
 * (a dozen nodes), the layout is a fixed circle sorted by (type, id), and the
 * result is identical every render — same seed, same picture, same demo.
 * Multi-edges (one per event in the MultiDiGraph) collapse into one line with
 * an event count.
 */

const TYPE_COLOR: Record<string, string> = {
  customer: "#22D3EE",
  server: "#22D3EE",
  account: "#E2E8F0",
  device: "#FBBF24",
  staff: "#34D399",
  payee: "#34D399",
  terminal: "#F59E0B",
  asn: "#F59E0B",
  ip: "#EF4444",
};

const MAX_NEIGHBORS = 14;
const W = 380;
const H = 264;
const CX = W / 2;
const CY = H / 2 + 4;
const R = 88;

export function EntityGraph({ entityId }: { entityId: string }) {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    setGraph(null);
    setFailed(false);
    getGraph(entityId).then((g) => {
      if (!alive) return;
      if (g === null) setFailed(true);
      else setGraph(g);
    });
    return () => {
      alive = false;
    };
  }, [entityId]);

  const layout = useMemo(() => {
    if (!graph) return null;
    const neighbors = graph.nodes
      .filter((n) => n.id !== entityId)
      .sort((a, b) => a.type.localeCompare(b.type) || a.id.localeCompare(b.id));
    const shown = neighbors.slice(0, MAX_NEIGHBORS);
    const hidden = neighbors.length - shown.length;

    const pos = new Map<string, { x: number; y: number }>();
    pos.set(entityId, { x: CX, y: CY });
    shown.forEach((n, i) => {
      // start at -90° so the first group sits on top; even angular spacing
      const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(shown.length, 1);
      pos.set(n.id, { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) });
    });

    // collapse multi-edges (one per event) into one line + count
    const collapsed = new Map<string, { src: string; dst: string; type: string; n: number }>();
    for (const e of graph.edges) {
      if (!pos.has(e.src) || !pos.has(e.dst)) continue;
      const key = [e.src, e.dst, e.type].join("|");
      const prev = collapsed.get(key);
      if (prev) prev.n += 1;
      else collapsed.set(key, { src: e.src, dst: e.dst, type: e.type, n: 1 });
    }

    const types = Array.from(new Set(shown.map((n) => n.type))).sort();
    return { shown, hidden, pos, edges: Array.from(collapsed.values()), types };
  }, [graph, entityId]);

  if (failed)
    return (
      <p className="py-4 text-center font-mono text-xs text-muted">
        graph unavailable for {entityId}
      </p>
    );
  if (!layout)
    return (
      <p className="py-4 text-center font-mono text-xs text-muted">
        loading neighborhood…
      </p>
    );

  const hub = layout.pos.get(entityId)!;
  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label={`Entity graph: ${layout.shown.length} entities within one hop of ${entityId}`}
      >
        {layout.edges.map((e) => {
          const a = layout.pos.get(e.src)!;
          const b = layout.pos.get(e.dst)!;
          return (
            <line
              key={`${e.src}|${e.dst}|${e.type}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="#24344E"
              strokeWidth={Math.min(1 + Math.log2(e.n), 4)}
            >
              <title>{`${e.type} ×${e.n} — ${e.src} → ${e.dst}`}</title>
            </line>
          );
        })}
        {layout.shown.map((n) => {
          const p = layout.pos.get(n.id)!;
          const c = TYPE_COLOR[n.type] ?? "#8B9BB4";
          return (
            <g key={n.id}>
              <rect
                x={p.x - 7}
                y={p.y - 7}
                width={14}
                height={14}
                fill="#080D18"
                stroke={c}
                strokeWidth={2}
              >
                <title>{`${n.type} ${n.id}`}</title>
              </rect>
              <text
                x={p.x}
                y={p.y + (p.y >= CY ? 20 : -12)}
                textAnchor="middle"
                fill="#8B9BB4"
                fontSize="9"
                fontFamily="var(--font-jetbrains), ui-monospace, monospace"
              >
                {n.id}
              </text>
            </g>
          );
        })}
        {/* hub on top */}
        <rect
          x={hub.x - 10}
          y={hub.y - 10}
          width={20}
          height={20}
          fill="#22D3EE"
          stroke="#080D18"
          strokeWidth={2}
        />
        <text
          x={hub.x}
          y={hub.y + 26}
          textAnchor="middle"
          fill="#E2E8F0"
          fontSize="11"
          fontWeight="700"
          fontFamily="var(--font-jetbrains), ui-monospace, monospace"
        >
          {entityId}
        </text>
      </svg>
      <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-wider text-muted">
        {layout.types.map((t) => (
          <span key={t} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2"
              style={{ border: `2px solid ${TYPE_COLOR[t] ?? "#8B9BB4"}` }}
            />
            {t}
          </span>
        ))}
        <span className="ml-auto">
          {layout.shown.length} entities · 1 hop
          {layout.hidden > 0 ? ` · +${layout.hidden} more` : ""}
        </span>
      </div>
    </div>
  );
}
