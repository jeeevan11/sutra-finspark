"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Panel, PqcReadyBadge, SeverityDot, StatusPill, severityColor } from "@/components/ui";
import { RESET_EVENT, useSutra } from "@/components/SutraProvider";
import { getQuantum } from "@/lib/api";
import { formatBytes, formatIST } from "@/lib/format";
import type { QuantumResponse } from "@/lib/types";

const KEX_COLUMNS: Array<{ key: string; label: string; vulnerable: boolean }> = [
  { key: "RSA-2048", label: "RSA-2048", vulnerable: true },
  { key: "ECDHE-P256", label: "ECDHE-P256", vulnerable: true },
  { key: "X25519", label: "X25519", vulnerable: true },
  { key: "X25519Kyber768-hybrid", label: "Kyber768 hybrid", vulnerable: false },
];

function HndlBar({ score }: { score: number }) {
  const s = Math.max(0, Math.min(100, score));
  const color = s >= 70 ? "#EF4444" : s >= 40 ? "#F59E0B" : "#34D399";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-edge">
        <div
          className="h-full rounded-full"
          style={{ width: `${s}%`, backgroundColor: color }}
        />
      </div>
      <span
        className="font-mono text-sm font-bold tabular-nums"
        style={{ color }}
      >
        {Math.round(s)}
      </span>
    </div>
  );
}

export default function QuantumPage() {
  const { backendUp } = useSutra();
  const [data, setData] = useState<QuantumResponse | null>(null);

  // Poll every 5s; clear on demo reset.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const res = await getQuantum();
      if (alive && res) setData(res);
    };
    void tick();
    const interval = setInterval(() => void tick(), 5000);
    const clear = () => setData(null);
    window.addEventListener(RESET_EVENT, clear);
    return () => {
      alive = false;
      clearInterval(interval);
      window.removeEventListener(RESET_EVENT, clear);
    };
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold tracking-wide">
          Quantum readiness — crypto inventory
        </h1>
        <p className="mt-1 max-w-[110ch] text-[13px] leading-relaxed text-muted">
          Harvest-now-decrypt-later: data exfiltrated today over
          quantum-vulnerable channels can be decrypted once a cryptographically
          relevant quantum computer exists.
        </p>
      </div>

      <Panel title="Crypto inventory">
        {data === null ? (
          <div className="flex min-h-[180px] items-center justify-center text-sm text-muted">
            {backendUp ? "loading inventory…" : "waiting for backend…"}
          </div>
        ) : data.assets.length === 0 ? (
          <div className="flex min-h-[180px] items-center justify-center text-sm text-muted">
            no assets observed yet — start the replay
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-edge text-[11px] uppercase tracking-wider text-muted">
                  <th className="px-4 py-2.5 font-medium">Asset</th>
                  <th className="px-2 py-2.5 font-medium">Kind</th>
                  {KEX_COLUMNS.map((c) => (
                    <th
                      key={c.key}
                      className={`px-2 py-2.5 text-right font-medium ${
                        c.vulnerable ? "" : "text-ok/80"
                      }`}
                      title={
                        c.vulnerable
                          ? "quantum-vulnerable key exchange"
                          : "post-quantum hybrid key exchange"
                      }
                    >
                      {c.label}
                    </th>
                  ))}
                  <th className="px-2 py-2.5 font-medium">PQC-ready</th>
                  <th className="px-2 py-2.5 font-medium">HNDL score</th>
                  <th className="px-2 py-2.5 text-right font-medium">
                    Bytes → unknown dst
                  </th>
                  <th className="px-4 py-2.5 font-medium">Last seen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge/60">
                {data.assets.map((a) => (
                  <tr key={a.asset_id} className="hover:bg-edge/30">
                    <td className="px-4 py-2.5 font-mono font-semibold text-body">
                      {a.asset_id}
                    </td>
                    <td className="px-2 py-2.5 text-xs text-muted">{a.kind}</td>
                    {KEX_COLUMNS.map((c) => {
                      const n = a.sessions_by_kex[c.key] ?? 0;
                      return (
                        <td
                          key={c.key}
                          className={`px-2 py-2.5 text-right font-mono text-xs tabular-nums ${
                            n === 0
                              ? "text-muted/50"
                              : c.vulnerable
                                ? "text-body"
                                : "text-ok"
                          }`}
                        >
                          {n}
                        </td>
                      );
                    })}
                    <td className="px-2 py-2.5">
                      <PqcReadyBadge ready={a.pqc_ready} />
                    </td>
                    <td className="px-2 py-2.5">
                      <HndlBar score={a.hndl_score} />
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono text-xs tabular-nums text-body">
                      {formatBytes(a.bytes_to_unknown)}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted">
                      {a.last_seen ? `${formatIST(a.last_seen)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="HNDL-flagged incidents">
        {data === null || data.hndl_incidents.length === 0 ? (
          <div className="flex min-h-[100px] items-center justify-center text-sm text-muted">
            {data === null
              ? backendUp
                ? "loading…"
                : "waiting for backend…"
              : "no quantum-tagged alerts"}
          </div>
        ) : (
          <ul className="divide-y divide-edge/60">
            {data.hndl_incidents.map((a) => (
              <li key={a.alert_id}>
                <Link
                  href={`/alerts/${a.alert_id}`}
                  className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-edge/40"
                >
                  <SeverityDot severity={a.severity} />
                  <span
                    className="w-8 font-mono text-base font-bold tabular-nums"
                    style={{ color: severityColor(a.severity) }}
                  >
                    {a.risk}
                  </span>
                  <span className="truncate text-sm text-body">{a.title}</span>
                  <span className="font-mono text-[11px] text-muted">
                    {a.alert_id} · {a.entity_id}
                  </span>
                  <span className="ml-auto shrink-0">
                    <StatusPill status={a.status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
