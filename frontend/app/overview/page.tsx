"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getMetrics, replayStart } from "@/lib/api";
import type { Metrics } from "@/lib/types";
import { useSutra } from "@/components/SutraProvider";

/**
 * /overview — the judges' cover screen. Brutalist bento: exposed grid, hard
 * corners, oversized numerals, status-color accents. Designed to fit ONE
 * viewport (no scroll) at ≥1280×800 so it screenshots clean, then funnel the
 * viewer into the live demo (START → Live Ops). Everything uses the pinned
 * SUTRA palette + self-hosted fonts; zero new dependencies, zero egress.
 */

// Deterministic seed-42 benchmark numbers as fallback; live metrics.json
// (same numbers unless the seed changes) replaces them when the API is up.
const FALLBACK = {
  siloed: 35,
  fused: 3,
  fp_siloed: 30,
  fp_fused: 0,
  reduction: 91.4,
  rupees: "₹19,99,700",
};

const TEAM = [
  { name: "Jatin Chhanwal", role: "Design & Engineering", link: "github.com/jeeevan11" },
];
const CONTACT_EMAIL = "specialistatseo@gmail.com";
const REPO_URL = "https://github.com/jeeevan11/sutra-finspark";

const CASES = [
  {
    index: "01",
    hex: "#EF4444",
    tag: "ATO · FRAUD",
    title: "Account takeover, structured out the door",
    body: "An attacker splits a takeover across two silos — each half looks routine alone.",
    trace: [
      ["t+0", "40× login FAIL · one hostile ASN · 15 accounts"],
      ["t+4m", "login OK CUST-0421 · unseen device · Bucharest"],
      ["t+6m", "payee+ PAYEE-MULE — never seen before"],
      ["t+9m", "UPI ₹49,900 ×3 — under the ₹50k line"],
    ],
    verdict: "6 rules correlate → risk 100 in 7s",
    siloed: "siloed: 3 fragments, buried",
  },
  {
    index: "02",
    hex: "#F59E0B",
    tag: "INSIDER · EDR",
    title: "Compromised branch terminal",
    body: "Two weak signals nobody joins: an endpoint ping and a big transfer.",
    trace: [
      ["t+0", "EDR med · TERM-114 · CobaltStrike beacon"],
      ["t+7m", "RTGS ₹18,50,000 · keyed 22:40 — off-hours"],
      ["", "source account dormant >90 days"],
      ["", "payee unknown · shell beneficiary"],
    ],
    verdict: "fused: two weak halves → critical",
    siloed: "siloed: max score 40, lost",
  },
  {
    index: "03",
    hex: "#22D3EE",
    tag: "QUANTUM · HNDL",
    title: "Harvest now, decrypt later",
    body: "Encrypted exfil today is plaintext the day a quantum computer exists.",
    trace: [
      ["t+0", "6× TLS 1.2 · RSA-2048 · DB-2 → unknown host"],
      ["t+10m", "4.2 GB cumulative vulnerable egress"],
      ["", "crypto inventory: DB-2 flips red"],
      ["", "alert signed ML-DSA-65 · chain-linked"],
    ],
    verdict: "flagged + ML-DSA-65 signed",
    siloed: "siloed: missed entirely",
  },
] as const;

const PIPELINE = ["TELEMETRY + TXNS", "ENTITY GRAPH", "R1–R11 ⊕ ISO-FOREST", "ML-DSA-65 ALERT"];

const PS2 = ["CORRELATE", "PROACTIVE", "FRAUD", "QUANTUM", "FP −91%", "EXPLAINABLE"];

export default function OverviewPage() {
  const router = useRouter();
  const { applyStatus, backendUp } = useSutra();
  const [m, setM] = useState<typeof FALLBACK>(FALLBACK);
  const [starting, setStarting] = useState(false);
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    getMetrics().then((data: Metrics | null) => {
      if (!data || !data.modes) return;
      setM({
        siloed: data.modes.siloed.total_alerts || FALLBACK.siloed,
        fused: data.modes.fused.total_alerts || FALLBACK.fused,
        fp_siloed: data.modes.siloed.false_positives,
        fp_fused: data.modes.fused.false_positives,
        reduction: data.summary.alert_reduction_pct || FALLBACK.reduction,
        rupees: FALLBACK.rupees,
      });
    });
  }, []);

  async function startDemo() {
    if (starting) return;
    setStarting(true);
    const res = await replayStart(20);
    if (res?.ok) applyStatus(res.status);
    router.push("/");
  }

  function sendMail() {
    const subject = encodeURIComponent("SUTRA — FinSpark'26 submission");
    const body = encodeURIComponent(`From: ${email}\n\n${message}`);
    window.location.href = `mailto:${CONTACT_EMAIL}?subject=${subject}&body=${body}`;
  }

  let cell = 0;
  const d = () => ({ "--ov-delay": `${cell++ * 45}ms` }) as React.CSSProperties;

  return (
    // The root layout wraps pages in <main class="px-5 pb-40 pt-5"> (dock
    // clearance). This cover page must fit EXACTLY one viewport, so cancel the
    // bottom clearance (no dock here) and size against nav(56)+pt(20)+pb(16).
    <div className="-mb-40 flex h-[calc(100dvh-92px)] w-full flex-col overflow-hidden">
      <div className="grid min-h-0 flex-1 grid-cols-12 grid-rows-[auto_minmax(0,1fr)_auto] gap-[3px] overflow-hidden border-2 border-edge bg-edge/70 p-[3px]">
        {/* ─────────────────────────── ROW A · masthead ─────────────────────── */}
        <section
          className="ov-cell col-span-12 flex items-start justify-between gap-6 bg-night px-6 py-5 lg:col-span-9"
          style={d()}
        >
          <div className="min-w-0">
            <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.3em] text-muted">
              <span className="inline-block h-2 w-2 bg-accent" />
              FinSpark&#39;26 · PS2 · Bank of Maharashtra
            </div>
            <h1 className="mt-2 font-mono text-[clamp(1.9rem,5.2vh,3.8rem)] font-extrabold uppercase leading-[0.95] tracking-tight text-body">
              Every signal.
              <br />
              One <span className="bg-accent px-2 text-night">verdict.</span>
            </h1>
            <p className="mt-3 max-w-[58ch] text-[clamp(0.8rem,1.6vh,0.95rem)] leading-snug text-body/70">
              SUTRA fuses security telemetry and core-banking transactions into
              one entity graph — so an attack split across two silos lands as a
              single, explainable, post-quantum-signed alert.
            </p>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-widest text-muted">
              {PS2.map((p) => (
                <span key={p}>
                  <span className="text-ok">✓</span> {p}
                </span>
              ))}
            </div>
          </div>
          {/* the how-it-works pipeline, exposed like a schematic */}
          <div className="hidden shrink-0 self-center border-l-2 border-edge pl-6 lg:block">
            {PIPELINE.map((step, i) => (
              <div key={step}>
                <div className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-widest text-body/80">
                  <span className="text-muted">{String(i + 1).padStart(2, "0")}</span>
                  <span className={i === PIPELINE.length - 1 ? "text-accent" : ""}>{step}</span>
                </div>
                {i < PIPELINE.length - 1 && (
                  <div className="ml-[3px] h-[clamp(8px,1.6vh,16px)] border-l-2 border-edge" />
                )}
              </div>
            ))}
          </div>
        </section>

        <section
          className="ov-cell col-span-12 flex flex-col justify-between bg-panel px-6 py-5 lg:col-span-3"
          style={d()}
        >
          <div className="font-mono text-[11px] uppercase tracking-[0.3em] text-muted">
            Alert noise
          </div>
          <div className="font-mono text-[clamp(2.6rem,7.5vh,5rem)] font-extrabold leading-none tracking-tighter text-ok">
            −{m.reduction}%
          </div>
          <div className="font-mono text-[11px] uppercase tracking-widest text-body/60">
            same telemetry · same day
            <br />
            {m.siloed} siloed alerts → {m.fused}
          </div>
        </section>

        {/* ─────────────────────────── ROW B · case previews ────────────────── */}
        {CASES.map((c) => (
          <article
            key={c.index}
            className="ov-cell ov-card relative col-span-6 flex min-h-0 flex-col overflow-hidden bg-night px-5 py-4 lg:col-span-3"
            style={{ ...d(), "--ov-shadow": c.hex, borderTop: `3px solid ${c.hex}` } as React.CSSProperties}
          >
            <span
              aria-hidden
              className="pointer-events-none absolute -right-1 -top-3 select-none font-mono text-[clamp(3.4rem,9vh,6rem)] font-extrabold leading-none text-edge/60"
            >
              {c.index}
            </span>
            <div className="font-mono text-[10px] uppercase tracking-[0.25em]" style={{ color: c.hex }}>
              {c.tag}
            </div>
            <h2 className="relative mt-2 text-[clamp(0.95rem,2vh,1.2rem)] font-bold leading-tight text-body">
              {c.title}
            </h2>
            <p className="mt-1.5 text-[clamp(0.72rem,1.45vh,0.85rem)] leading-snug text-body/60">
              {c.body}
            </p>
            {/* deterministic kill-chain trace — the case study, replayable live */}
            <div className="mt-2 flex min-h-0 flex-1 flex-col justify-end gap-[clamp(3px,1.1vh,14px)] overflow-hidden">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted">
                  evidence replay
                </span>
                <span className="h-px flex-1 bg-edge" />
              </div>
              {c.trace.map(([t, line], ti) => (
                <div key={ti} className="flex items-baseline gap-2 font-mono text-[clamp(0.66rem,1.45vh,0.84rem)] leading-tight">
                  <span className="w-11 shrink-0 text-right text-muted">{t}</span>
                  <span className="shrink-0" style={{ color: c.hex }}>
                    ▸
                  </span>
                  <span className="truncate text-body/75">{line}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 border-t-2 border-edge pt-2">
              <div className="font-mono text-[11px] font-bold uppercase tracking-wide" style={{ color: c.hex }}>
                {c.verdict}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-wide text-muted line-through decoration-muted/60">
                {c.siloed}
              </div>
            </div>
          </article>
        ))}

        <section className="ov-cell col-span-6 flex min-h-0 flex-col gap-[3px] bg-transparent lg:col-span-3" style={d()}>
          {/* team */}
          <div className="bg-panel px-5 py-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted">Team</div>
            {TEAM.map((t) => (
              <div key={t.name} className="mt-1.5">
                <div className="text-sm font-bold uppercase tracking-wide text-body">{t.name}</div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-body/50">{t.role}</div>
                <a
                  href={REPO_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block border border-edge px-1.5 py-0.5 font-mono text-[10px] text-accent hover:border-accent"
                >
                  {t.link} ↗
                </a>
              </div>
            ))}
          </div>
          {/* contact */}
          <form
            className="flex min-h-0 flex-1 flex-col bg-night px-5 py-3"
            onSubmit={(e) => {
              e.preventDefault();
              sendMail();
            }}
          >
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted">Contact</div>
            <label htmlFor="ov-email" className="mt-1.5 font-mono text-[9px] uppercase tracking-widest text-body/50">
              Email
            </label>
            <input
              id="ov-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-0.5 border-2 border-edge bg-panel px-2 py-1 font-mono text-xs text-body outline-none focus:border-accent"
            />
            <label htmlFor="ov-msg" className="mt-1.5 font-mono text-[9px] uppercase tracking-widest text-body/50">
              Message
            </label>
            <input
              id="ov-msg"
              type="text"
              required
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className="mt-0.5 border-2 border-edge bg-panel px-2 py-1 font-mono text-xs text-body outline-none focus:border-accent"
            />
            <button
              type="submit"
              className="mt-2 border-2 border-accent px-2 py-1 font-mono text-[11px] font-bold uppercase tracking-widest text-accent transition-colors hover:bg-accent hover:text-night active:scale-[0.98]"
            >
              Send ↗
            </button>
            <div className="flex-1" />
            <p className="mt-2 font-mono text-[9px] uppercase leading-relaxed tracking-wider text-muted">
              opens your mail client —
              <br />
              zero runtime network egress
            </p>
          </form>
        </section>

        {/* ─────────────────────────── ROW C · proof + CTA ──────────────────── */}
        {[
          { k: "Alerts / day", v: `${m.siloed}→${m.fused}`, c: "text-body" },
          { k: "False positives", v: `${m.fp_siloed}→${m.fp_fused}`, c: "text-ok" },
          { k: "Scenario recall", v: "3/3", c: "text-accent" },
          { k: "Outflow flagged", v: m.rupees, c: "text-high" },
        ].map((s) => (
          <div key={s.k} className="ov-cell col-span-3 bg-panel px-4 py-3 lg:col-span-2" style={d()}>
            <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted">{s.k}</div>
            <div className={`mt-1 font-mono text-[clamp(1rem,2.6vh,1.6rem)] font-extrabold tracking-tight ${s.c}`}>
              {s.v}
            </div>
          </div>
        ))}

        <button
          onClick={() => void startDemo()}
          disabled={starting}
          className="ov-cell col-span-8 flex items-center justify-between bg-accent px-5 py-3 text-night transition-colors hover:bg-body active:scale-[0.99] disabled:opacity-60 lg:col-span-2"
          style={d()}
        >
          <span className="font-mono text-[clamp(0.85rem,1.9vh,1.05rem)] font-extrabold uppercase tracking-widest">
            {starting ? "Starting…" : backendUp ? "Start demo" : "Open console"}
          </span>
          <span aria-hidden className="font-mono text-xl font-extrabold">
            →
          </span>
        </button>

        <div
          className="ov-cell ov-hatch relative col-span-4 flex flex-col justify-between bg-night px-4 py-3 lg:col-span-2"
          style={d()}
        >
          <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted">
            seed 42 · deterministic
          </span>
          <Link
            href="/metrics"
            className="self-start bg-night font-mono text-[11px] font-bold uppercase tracking-widest text-body/70 hover:text-accent"
          >
            benchmark →
          </Link>
        </div>
      </div>
    </div>
  );
}
