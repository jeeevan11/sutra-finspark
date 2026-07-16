"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { replayInject, replayPause, replayReset, replayStart } from "@/lib/api";
import { formatIST } from "@/lib/format";
import type { ReplaySpeed, Scenario } from "@/lib/types";
import { RESET_EVENT, useSutra } from "./SutraProvider";

const SPEEDS: ReplaySpeed[] = [1, 5, 20];
const SCENARIOS: Scenario[] = ["A", "B", "C"];

export function DemoDock() {
  const { status, backendUp, applyStatus } = useSutra();
  const [speed, setSpeed] = useState<ReplaySpeed>(20);
  const [flash, setFlash] = useState<Record<string, number>>({});
  const [resetArmed, setResetArmed] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );

  const running = backendUp && status !== null && status.running;
  const paused = running && status !== null && status.paused;

  const showToast = useCallback((text: string) => {
    setToast(text);
    if (toastTimer.current !== undefined) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2200);
  }, []);

  const togglePause = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    const res = running ? await replayPause() : await replayStart(speed);
    if (res?.ok) applyStatus(res.status);
    else if (!res) showToast("backend unreachable");
    setBusy(false);
  }, [busy, running, speed, applyStatus, showToast]);

  const changeSpeed = useCallback(
    async (s: ReplaySpeed) => {
      setSpeed(s);
      // If the replay is already running, restart it at the chosen speed.
      if (running) {
        const res = await replayStart(s);
        if (res?.ok) applyStatus(res.status);
      }
    },
    [running, applyStatus],
  );

  const inject = useCallback(
    async (sc: Scenario) => {
      const res = await replayInject(sc);
      if (res?.ok) {
        applyStatus(res.status);
        setFlash((f) => ({ ...f, [sc]: Date.now() }));
        showToast(`scenario ${sc} injected`);
      } else {
        showToast("inject failed — backend unreachable");
      }
    },
    [applyStatus, showToast],
  );

  const disarmReset = useCallback(() => {
    setResetArmed(false);
    if (resetTimer.current !== undefined) clearTimeout(resetTimer.current);
  }, []);

  const requestReset = useCallback(async () => {
    if (!resetArmed) {
      setResetArmed(true);
      showToast("press r again to confirm reset");
      if (resetTimer.current !== undefined) clearTimeout(resetTimer.current);
      resetTimer.current = setTimeout(() => setResetArmed(false), 2000);
      return;
    }
    disarmReset();
    const res = await replayReset();
    if (res?.ok) {
      applyStatus(res.status);
      // Broadcast so rivers / feeds clear their client-side buffers.
      window.dispatchEvent(new CustomEvent(RESET_EVENT));
      showToast("world reset");
    } else {
      showToast("reset failed — backend unreachable");
    }
  }, [resetArmed, disarmReset, applyStatus, showToast]);

  // Global keyboard shortcuts: 1/2/3 inject, space pause/resume, r reset.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.isContentEditable)
      ) {
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "1") void inject("A");
      else if (e.key === "2") void inject("B");
      else if (e.key === "3") void inject("C");
      else if (e.key === " ") {
        e.preventDefault();
        void togglePause();
      } else if (e.key === "r" || e.key === "R") {
        void requestReset();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [inject, togglePause, requestReset]);

  useEffect(
    () => () => {
      if (resetTimer.current !== undefined) clearTimeout(resetTimer.current);
      if (toastTimer.current !== undefined) clearTimeout(toastTimer.current);
    },
    [],
  );

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[300px] select-none">
      {toast && (
        <div className="mb-2 rounded border border-edge bg-panel px-3 py-2 text-xs text-body shadow-lg">
          {toast}
        </div>
      )}
      <div className="rounded-lg border border-edge bg-panel/95 p-3 shadow-xl backdrop-blur">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
            Demo control
          </span>
          <span className="font-mono text-[11px] text-muted">
            {!backendUp ? (
              "offline"
            ) : status ? (
              <>
                <span
                  className={
                    status.running
                      ? status.paused
                        ? "text-high"
                        : "text-ok"
                      : "text-muted"
                  }
                >
                  {status.running
                    ? status.paused
                      ? "paused"
                      : "running"
                    : "stopped"}
                </span>
                <span className="text-muted"> · {formatIST(status.sim_time)} IST</span>
              </>
            ) : (
              "…"
            )}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => void togglePause()}
            disabled={busy}
            className={`h-9 flex-1 rounded border text-sm font-semibold transition-colors disabled:opacity-50 ${
              running && !paused
                ? "border-high/60 text-high hover:bg-high/10"
                : "border-ok/60 text-ok hover:bg-ok/10"
            }`}
          >
            {!running ? "▶ Start" : paused ? "▶ Resume" : "❚❚ Pause"}
          </button>

          <div className="flex overflow-hidden rounded border border-edge">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => void changeSpeed(s)}
                className={`px-2.5 py-2 font-mono text-xs transition-colors ${
                  speed === s
                    ? "bg-accent/20 text-accent"
                    : "text-muted hover:bg-edge/60 hover:text-body"
                }`}
              >
                ×{s}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-2 grid grid-cols-3 gap-2">
          {SCENARIOS.map((sc) => (
            <button
              key={`${sc}-${flash[sc] ?? 0}`}
              onClick={() => void inject(sc)}
              className={`h-8 rounded border border-edge font-mono text-xs text-body/90 transition-colors hover:border-accent/60 hover:text-accent ${
                flash[sc] ? "btn-flash" : ""
              }`}
              title={`Inject scenario ${sc} (key ${sc === "A" ? 1 : sc === "B" ? 2 : 3})`}
            >
              Inject {sc}
            </button>
          ))}
        </div>

        <div className="mt-2">
          <button
            onClick={() => void requestReset()}
            className={`h-8 w-full rounded border font-mono text-xs transition-colors ${
              resetArmed
                ? "border-critical bg-critical/20 text-critical"
                : "border-edge text-muted hover:border-critical/60 hover:text-critical"
            }`}
          >
            {resetArmed ? "sure? click again to reset" : "Reset world (r)"}
          </button>
        </div>

        <div className="mt-2 flex justify-between gap-2 whitespace-nowrap font-mono text-[10px] text-muted/80">
          <span>1/2/3 inject · spc pause · r reset</span>
          {status && backendUp && <span>{status.events_emitted} ev</span>}
        </div>
      </div>
    </div>
  );
}
