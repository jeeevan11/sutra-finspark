"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { EntityGraph } from "@/components/EntityGraph";
import { EvidenceTimeline } from "@/components/EvidenceTimeline";
import { RiskGauge } from "@/components/RiskGauge";
import { RuleBreakdown } from "@/components/RuleBreakdown";
import { Panel, SeverityChip, StatusPill } from "@/components/ui";
import { useSutra } from "@/components/SutraProvider";
import { getAlert, postAlertAction, verifyAlert } from "@/lib/api";
import { formatIST, formatISTFull } from "@/lib/format";
import type {
  ActionType,
  AlertDetail,
  AlertStatus,
  VerifyResponse,
} from "@/lib/types";

const ACTIONS: Array<{
  action: ActionType;
  label: string;
  doneLabel: string;
  matches: AlertStatus;
  cls: string;
  doneCls: string;
}> = [
  {
    action: "hold",
    label: "Hold transactions",
    doneLabel: "Transactions held",
    matches: "held",
    cls: "border-critical/60 text-critical hover:bg-critical/10",
    doneCls: "border-critical bg-critical text-night",
  },
  {
    action: "stepup",
    label: "Force step-up",
    doneLabel: "Step-up forced",
    matches: "stepup",
    cls: "border-high/60 text-high hover:bg-high/10",
    doneCls: "border-high bg-high text-night",
  },
  {
    action: "dismiss",
    label: "Dismiss",
    doneLabel: "Dismissed",
    matches: "dismissed",
    cls: "border-edge text-muted hover:bg-edge/50 hover:text-body",
    doneCls: "border-muted bg-muted text-night",
  },
];

type VerifyState =
  | { phase: "idle" }
  | { phase: "pending" }
  | { phase: "error" }
  | { phase: "done"; result: VerifyResponse };

export default function AlertDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const id = params.id;
  const { backendUp } = useSutra();
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [inFlight, setInFlight] = useState<ActionType | null>(null);
  const [lastActionResult, setLastActionResult] = useState<string | null>(null);
  const [verify, setVerify] = useState<VerifyState>({ phase: "idle" });
  const actionInFlightRef = useRef(false);

  // Poll the detail every 3s so evidence grows live; pause during actions.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (!actionInFlightRef.current) {
        const d = await getAlert(id);
        if (!alive) return;
        if (d) setDetail(d);
        setLoadedOnce(true);
      }
      timer = setTimeout(tick, 3000);
    };
    void tick();
    return () => {
      alive = false;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [id]);

  const runAction = useCallback(
    async (action: ActionType) => {
      if (actionInFlightRef.current) return;
      actionInFlightRef.current = true;
      setInFlight(action);
      const res = await postAlertAction(id, action);
      if (res?.ok) {
        setDetail((d) =>
          d ? { ...d, status: res.status as AlertStatus } : d,
        );
        setLastActionResult(res.result);
      } else {
        setLastActionResult("action failed — backend unreachable");
      }
      setInFlight(null);
      actionInFlightRef.current = false;
    },
    [id],
  );

  const runVerify = useCallback(async () => {
    setVerify({ phase: "pending" });
    const res = await verifyAlert(id);
    if (res) setVerify({ phase: "done", result: res });
    else setVerify({ phase: "error" });
  }, [id]);

  if (!detail) {
    return (
      <div className="flex min-h-[300px] items-center justify-center text-sm text-muted">
        {!loadedOnce
          ? "loading alert…"
          : backendUp
            ? `alert ${id} not found`
            : "waiting for backend…"}
      </div>
    );
  }

  const verified =
    verify.phase === "done" &&
    verify.result.signature_valid &&
    verify.result.chain_valid;
  const tampered = verify.phase === "done" && !verified;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <Panel className="px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
          <RiskGauge risk={detail.risk} severity={detail.severity} />
          <div className="min-w-[280px] flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="font-mono text-xs text-muted">
                {detail.alert_id}
              </span>
              <SeverityChip severity={detail.severity} />
              <StatusPill status={detail.status} />
              {detail.tags.includes("quantum") && (
                <span className="rounded-full border border-ok/50 bg-ok/10 px-2.5 py-0.5 font-mono text-[11px] text-ok">
                  QUANTUM / HNDL
                </span>
              )}
              {detail.tags
                .filter((t) => /^T\d{4}/.test(t))
                .map((t) => (
                  <span
                    key={t}
                    title={`MITRE ATT&CK ${t}`}
                    className="rounded-full border border-edge bg-panel px-2.5 py-0.5 font-mono text-[11px] text-body/70"
                  >
                    ATT&amp;CK {t}
                  </span>
                ))}
            </div>
            <h1 className="mt-2 text-xl font-semibold leading-snug text-body">
              {detail.title}
            </h1>
            <p className="mt-1 font-mono text-xs text-muted">
              {detail.entity_type} {detail.entity_id} · created{" "}
              {formatISTFull(detail.created_ts)} IST · updated{" "}
              {formatIST(detail.updated_ts)} IST
            </p>
          </div>

          {/* PQC badge + verify */}
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              {verified ? (
                <span className="rounded-full border border-ok/60 bg-ok/15 px-3 py-1 font-mono text-xs font-semibold text-ok">
                  ML-DSA-65 signed ✓
                </span>
              ) : tampered ? (
                <span className="rounded-full border border-critical/60 bg-critical/15 px-3 py-1 font-mono text-xs font-semibold text-critical">
                  TAMPERED ✗
                </span>
              ) : (
                <span className="rounded-full border border-edge px-3 py-1 font-mono text-xs text-muted">
                  ML-DSA-65 · not verified
                </span>
              )}
              <button
                onClick={() => void runVerify()}
                disabled={verify.phase === "pending"}
                className="rounded border border-accent/60 px-3 py-1 font-mono text-xs text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
              >
                {verify.phase === "pending" ? "Verifying…" : "Verify"}
              </button>
            </div>
            {verify.phase === "done" && (
              <p className="font-mono text-[11px] text-muted">
                signature{" "}
                <span
                  className={
                    verify.result.signature_valid ? "text-ok" : "text-critical"
                  }
                >
                  {verify.result.signature_valid ? "valid" : "INVALID"}
                </span>{" "}
                · chain{" "}
                <span
                  className={
                    verify.result.chain_valid ? "text-ok" : "text-critical"
                  }
                >
                  {verify.result.chain_valid ? "valid" : "BROKEN"}
                </span>{" "}
                · key {verify.result.pubkey_fingerprint}
              </p>
            )}
            {verify.phase === "error" && (
              <p className="font-mono text-[11px] text-high">
                verify unavailable — backend unreachable
              </p>
            )}
            <p className="font-mono text-[10px] text-muted/70">
              prev {detail.prev_hash.slice(0, 16)}
              {detail.prev_hash.length > 16 ? "…" : ""} · fp{" "}
              {detail.pubkey_fingerprint}
            </p>
          </div>
        </div>
      </Panel>

      {/* Narrative + actions */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
        <div className="flex flex-col gap-4">
          <Panel title="Narrative" className="px-5 py-4">
            <p className="max-w-[85ch] pt-2 text-[15.5px] leading-relaxed text-body/95">
              {detail.narrative}
            </p>
          </Panel>

          <Panel title="Entity graph — 1-hop neighborhood" className="px-5 py-4">
            <EntityGraph entityId={detail.entity_id} />
          </Panel>

          <Panel title="Evidence chain" className="px-5 py-4">
            <div className="pt-2">
              <EvidenceTimeline evidence={detail.evidence} />
            </div>
          </Panel>
        </div>

        <div className="flex flex-col gap-4">
          <Panel title="Response actions" className="px-5 py-4">
            <div className="flex flex-col gap-2 pt-2">
              {ACTIONS.map((a) => {
                const confirmed = detail.status === a.matches;
                const busy = inFlight === a.action;
                return (
                  <button
                    key={a.action}
                    onClick={() => void runAction(a.action)}
                    disabled={inFlight !== null || confirmed}
                    className={`h-10 rounded border text-sm font-semibold transition-colors disabled:cursor-not-allowed ${
                      confirmed ? a.doneCls : `${a.cls} disabled:opacity-50`
                    }`}
                  >
                    {confirmed
                      ? `✓ ${a.doneLabel}`
                      : busy
                        ? "Executing…"
                        : a.label}
                  </button>
                );
              })}
              {lastActionResult && (
                <p className="mt-1 font-mono text-xs text-accent">
                  {lastActionResult}
                </p>
              )}
              {detail.actions.length > 0 && (
                <ul className="mt-2 space-y-1 border-t border-edge pt-2">
                  {detail.actions.map((rec, i) => (
                    <li
                      key={`${rec.action}-${rec.ts}-${i}`}
                      className="font-mono text-[11px] text-muted"
                    >
                      {formatIST(rec.ts)} · {rec.action} — {rec.result}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Panel>

          <Panel title="Rule-hit breakdown" className="px-5 py-4">
            <div className="pt-2">
              <RuleBreakdown
                ruleHits={detail.rule_hits}
                mlScore={detail.ml_score}
              />
            </div>
          </Panel>

          <Panel title="Signature" className="px-5 py-4">
            <p className="break-all pt-2 font-mono text-[10px] leading-relaxed text-muted">
              {detail.signature.slice(0, 256)}
              {detail.signature.length > 256 ? "…" : ""}
            </p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
