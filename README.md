# SUTRA — Security Unified Telemetry & Risk Analytics

**FinSpark'26 · Bank of Maharashtra national cybersecurity hackathon · Problem Statement 2**

SUTRA is an open-source, on-prem correlation engine that fuses a bank's **security
telemetry** (logins, EDR alerts, TLS/network metadata) with its **core-banking
transaction stream** into one entity graph, scores risk with a rules + ML ensemble,
and produces **explainable alerts** — an evidence chain, a plain-English narrative,
and a one-click response. Every alert is signed with a **post-quantum signature**
(ML-DSA-65 / Dilithium) and hash-chained, and a **quantum-risk panel** flags
harvest-now-decrypt-later (HNDL) exposure.

## Why it exists

Banks run a SOC and a fraud team as silos. Account takeovers, compromised terminals
and structuring attacks live in the gap — each system sees a low-risk half of the
story. SUTRA is the missing correlation layer. On our seeded 24-hour benchmark it
turns **35 fragmented siloed alerts (30 false positives) into 3 precise alerts with
zero false positives** — a **91.4% cut in alert volume** at **100% recall** of the
three planted attacks, ≈**10.7 analyst-hours saved per day**.

## 60-second quickstart

```bash
git clone <this-repo> sutra && cd sutra
cp .env.example .env
docker compose up            # redis + backend:8000 + frontend:3000, ~60–90s first build
# then, once http://localhost:3000 is live:
make demo                    # starts the live replay at ×20
```

Open **http://localhost:3000**, then drive the demo entirely from the floating
**demo dock** (bottom-right): **Start**, then keys **`1`/`2`/`3`** to inject the
three attack scenarios, **`space`** to pause, **`r`** twice to reset. See
[`deliverables/DEMO_SCRIPT.md`](deliverables/DEMO_SCRIPT.md) for the 3-minute
choreography.

Runs on a plain laptop, **fully offline** — no external API calls at runtime.

### Without Docker (local dev)

```bash
make dev-backend    # uvicorn on :8000, in-memory bus (no Redis needed)
make dev-frontend   # next dev on :3000
make test           # full pytest suite
make bench          # regenerate the siloed-vs-fused benchmark
```

## What the judges can verify (PS2 expected outcomes)

| # | PS2 outcome | Where to see it |
|---|---|---|
| 1 | Correlates cyber telemetry with transactional behaviour | Any alert's evidence chain mixes logins/EDR/TLS **and** transactions; incident fusion merges them into one alert |
| 2 | Detects cyber threats proactively | Scenario A (credential stuffing → account takeover) fires a critical alert mid-attack |
| 3 | Identifies fraud patterns | R4 structuring, R5 velocity, R9 dormant-account, R11 unknown-payee rules |
| 4 | Detects quantum-related attack indicators | Scenario C → `/quantum` HNDL panel; R8 flags bulk egress over vulnerable key exchange |
| 5 | Reduces false positives | `/metrics`: 30 siloed FPs → **0** fused FPs; 30 borderline lookalikes suppressed |
| 6 | Explainable AI-driven threat intelligence | Every alert has a narrative, ranked rule-hit breakdown, ML anomaly score, full evidence timeline |

## The three demo scenarios

- **A — Account takeover + structuring.** A credential-stuffing burst from a hostile
  ASN, a takeover login from a new device, a new mule payee, then 3 × ₹49,900 UPI
  transfers under the reporting threshold. → one critical alert, risk ≥ 90.
- **B — Compromised branch terminal.** An EDR alert on a teller terminal, then an
  ₹18,50,000 RTGS from that same terminal, off-hours, draining a dormant corporate
  account. Each signal is sub-threshold alone; **correlation is the product**. → risk ≥ 85.
- **C — HNDL exfiltration.** A database moves 4.2 GB to an unknown host over RSA-2048.
  → quantum-tagged alert, DB-2 goes red on the crypto inventory. → risk ≥ 80.

## Security posture (30% of the rubric)

- **Post-quantum, tamper-evident audit.** Alerts are canonical-JSON'd, SHA-256'd and
  signed with **ML-DSA-65** (NIST FIPS 204), then hash-chained. `GET
  /api/alerts/{id}/verify` re-checks signature **and** chain; the demo tamper endpoint
  shows verification flipping to ✗ live.
- **No data egress.** Zero external/proprietary API calls at runtime. Narratives are
  deterministic Jinja templates, not an LLM — offline and hallucination-proof.
- **Threat-aware by design.** Deployment model is read-only taps on syslog/CEF + a
  transaction feed; detection mode makes **zero** changes to core banking.
- **Quantum readiness.** Live crypto inventory per asset with PQC-readiness badges and
  HNDL exposure scoring.

## Stack

Python 3.11 · FastAPI · pydantic v2 · SQLAlchemy + SQLite (WAL) · Redis Streams ·
networkx · scikit-learn (IsolationForest) · Jinja2 · dilithium-py (ML-DSA-65) —
backend. Next.js 14 · TypeScript · Tailwind · Recharts — frontend. Everything
open-source; the finished app runs air-gapped.

## Screenshots

Captured from the running Docker stack — see [`deliverables/screenshots/`](deliverables/screenshots/):

- [Overview cover page](deliverables/screenshots/overview.png) — scenario case previews, benchmark stats, START DEMO flow (`/overview`)
- [Live Ops mid-Scenario A](deliverables/screenshots/live-ops-scenario-a.png) — both event rivers flowing, the critical account-takeover alert in the feed
- [Alert detail "money screen"](deliverables/screenshots/alert-detail-scenario-a.png) — narrative, entity-graph neighborhood, full evidence chain, rule-hit breakdown, MITRE ATT&CK tags, ML-DSA-65 signature
- [Fused-vs-siloed benchmark](deliverables/screenshots/metrics.png) — −91.4% alert volume, 0 false positives
- [HNDL crypto inventory](deliverables/screenshots/quantum.png) — DB-2 flagged quantum-vulnerable red

## Honest limitations

- All data is **synthetic**, generated by the seeded world in `backend/sutra/generator/`.
  The generator ships in the repo — the benchmark is fully reproducible (`make bench`)
  but is not a claim about any specific real bank's traffic.
- Siloed mode is a faithful *approximation* of a split SIEM + FRM stack, not a
  benchmark of a named commercial product (see `deliverables/benchmark_report.md`).
- Single-node prototype. The scale-out path (Kafka/Flink, partition by entity,
  stateless workers, HSM-held signing keys) is designed but not implemented — see
  [`ARCHITECTURE.md`](ARCHITECTURE.md).
- No authentication (demo prototype). Production would sit behind the bank's SSO.

## PoC → production roadmap

1. Swap the in-memory event ring + Redis Streams for Kafka partitioned by entity;
   move fusion to stateless workers keyed on the same partition.
2. Replace SQLite with the bank's system-of-record; move ML-DSA keys into an HSM.
3. Real connectors: syslog/CEF collector, EDR webhook, core-banking read replica.
4. Analyst feedback loop to retrain the anomaly model; per-branch rule tuning.
5. PDF case-report export, optional local-LLM narrative toggle. (Per-alert MITRE
   ATT&CK tagging and the 1-hop entity-graph view already ship on the alert-detail
   page.)

## Repo layout

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full map and data flow.
`CLAUDE.md` documents conventions; `DECISIONS.md` records every non-obvious call;
`API_CONTRACT.md` pins the REST/WS shapes.

## License

Prototype for hackathon evaluation. All dependencies are open-source.
