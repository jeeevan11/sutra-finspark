# SUTRA architecture

## System diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          SUTRA backend (one process)                       │
│                                                                            │
│  generator/                     bus.py            fusion pipeline           │
│  ┌───────────┐  events   ┌──────────────┐   ┌──────────────────────────┐   │
│  │  world    │──────────▶│ Redis Streams│──▶│ graph.py (entity graph)  │   │
│  │  noise    │  (live)   │  group       │   │   ↓ neighborhood()       │   │
│  │  scenarios│           │  sutra-core  │   │ rules/engine.py R1–R11   │   │
│  │  replay   │           │ (or memory)  │   │   ↓ hits                 │   │
│  └───────────┘           └──────────────┘   │ ml/model.py IsolationF.  │   │
│       ▲  live x1/x5/x20                      │   ↓ score 0–40           │   │
│       │  inject A/B/C                        │ fusion.py                │   │
│       │                                      │   risk = 0.65·pts+0.35·ml │   │
│       │                                      │   incident correlation   │   │
│  ┌────┴─────┐                                │   ↓ Alert                │   │
│  │ REST api │◀───────────────────────────────┤ explain.py (Jinja)       │   │
│  │ ws hub   │   alerts / events               │ pqc.py (ML-DSA-65 sign)  │   │
│  └────┬─────┘                                │ quantum.py (HNDL)        │   │
│       │                                      │ store.py (SQLite WAL)    │   │
└───────┼──────────────────────────────────────┴──────────────────────────┘  │
        │ REST + WebSocket (CORS localhost:3000)
        ▼
┌──────────────────────┐
│  Next.js 14 frontend │  Overview · Live Ops · Alerts · Alert detail · Metrics · Quantum
│  + demo control dock │  (dark SOC console, WebSocket rivers, entity-graph + MITRE
└──────────────────────┘   tags on alert detail, PQC verify)
```

## Data flow (one event)

1. **Generate.** `replay.py` emits a benign or scenario event (live: sim clock ×
   speed; batch: a full 24h with no sleeps). Live mode strips the ground-truth
   `scenario` label before the bus; batch mode keeps it for the benchmark.
2. **Bus.** `bus.py` publishes to Redis Streams (consumer group `sutra-core`) or an
   in-process queue (`SUTRA_BUS=memory`). Batch/benchmark bypasses the bus and feeds
   fusion directly for determinism and speed.
3. **Graph.** `graph.py` upserts typed nodes/edges. `neighborhood(entity, window,
   now)` returns recent events touching an entity's 1-hop neighborhood — the
   correlation primitive.
4. **Rules.** `rules/engine.py` evaluates R1–R11 over the event and taints entities
   (a credential-stuffing ASN, a compromised terminal). Config/points/windows live in
   `rules/rules.yaml`, hot-reloaded on change.
5. **ML.** `ml/model.py` (IsolationForest, trained once on a benign day) scores the
   involved customer/staff 0–40 — but only after rules reach 25 points, so ML can
   never raise an alert alone.
6. **Fuse.** `fusion.py` computes `risk = min(100, 0.65·Σ points + 0.35·(ml·2.5))`,
   merges hits that share entities into one entity-set incident (45-min window), and
   fires an alert at risk ≥ 60.
7. **Explain + sign.** `explain.py` fills a Jinja narrative template; `pqc.py` signs
   the alert (ML-DSA-65) and links it into the hash chain; `store.py` appends the
   signed record to SQLite.
8. **Stream.** `ws.py` pushes the event to `/ws/events` (throttled 30 msg/s,
   drop-oldest) and any alert create/update to `/ws/alerts`.

## Key design / trust decisions

- **Templates over LLM for narratives.** Deterministic, offline, hallucination-proof,
  and auditable — the same evidence always yields the same words. An optional
  local-LLM toggle (Ollama) is on the roadmap but templates stay the source of truth.
- **ML-DSA-65 over classical signatures.** The audit trail must outlive the arrival of
  quantum computers (the same HNDL threat SUTRA detects applies to its own logs). A
  hash chain over signed records makes any single-record tamper — including of the
  chain tail — detectable.
- **Entity-set incidents, not per-entity.** An attack spans customer, device, ASN,
  account and payee; correlating on shared entities collapses a whole campaign into
  one alert instead of one-per-entity noise. This is the mechanism behind the 91%
  alert-volume reduction.
- **Rules carry the demo; ML sharpens.** ML degrades gracefully to 0 on any failure
  and can never fire an alert by itself — reliability first, per the hackathon brief.
- **Synthetic, seeded data.** No real PII; identical every run so the live demo can
  never diverge from rehearsal.

## Deployment story (on-prem, air-gapped)

- **Detection mode changes nothing in core banking.** SUTRA consumes **read-only taps**:
  a syslog/CEF collector for security telemetry and a read replica / message feed for
  the transaction stream. Response actions (hold / step-up) go through a thin adapter
  the bank authorizes separately — in the prototype it's mocked with 300 ms latency.
- **No egress.** Everything runs inside the bank's perimeter; no CDN, no cloud model,
  no telemetry. Verified by running with networking disabled.
- **Keys.** ML-DSA keys live under `DATA_DIR/keys` in the prototype; production moves
  them into an HSM.

## Scaling path

- **Bus → Kafka**, topic partitioned by entity id. The consumer is already a group
  member, so horizontal scale is a partition-count change.
- **Fusion → stateless workers** keyed on the same partition (an entity's events
  always land on the same worker, so incident state stays local). Rolling-window
  state moves to Redis / RocksDB.
- **Graph → a windowed store** (e.g. Flink keyed state or a graph DB) instead of an
  in-process networkx graph; the `neighborhood()` contract is unchanged.
- **Store → the bank's system-of-record**; the signed-record schema is already
  append-only and chain-linked.
- Throughput today: the single-process pipeline scores the full 101k-event batch day
  in ~1.5 s (~68k events/s) on a laptop — headroom for a mid-size bank before any of
  the above is needed.
