# SUTRA Build Plan

Maps the FinSpark'26 PS2 spec to concrete build phases. `make` is law; every phase ends
with `make test` green and a git commit `phase N: <summary>`.

## Phase 0 — Scaffold
- Repo root = this directory (opened workspace; empty, so no `sutra/` nesting — see DECISIONS.md).
- `git init`, `.gitignore`, `PLAN.md`, `DECISIONS.md`, `CLAUDE.md`, `.env.example`.
- `docker-compose.yml` (redis, backend:8000, frontend:3000, healthchecks).
- `Makefile`: `up demo bench test deliverables export-sample-data dev-backend dev-frontend`.
- `backend/requirements.txt` + venv; validate `dilithium-py` installs and signs/verifies.
- `API_CONTRACT.md`: exact JSON shapes for every REST/WS endpoint (frontend builds against
  this in parallel with the backend).

## Phase 1 — Synthetic world, scenarios, replay
- `sutra/config.py` (SUTRA_SEED=42 default, env-driven), `sutra/schemas.py` (pydantic v2
  models for all 6 event types + Alert/RuleHit/Evidence/Action).
- `generator/world.py`: 500 customers (accounts, devices, geo, txn baseline, payees,
  dormancy), 40 staff + terminals + hours, branch IPs, benign/hostile ASNs, servers with
  crypto posture.
- `generator/noise.py`: Poisson benign streams tuned to never alert at fused threshold.
- `generator/scenarios.py`: attacks A/B/C as deterministic sequences + ~30 borderline
  patterns (4 archetypes) that FP in siloed mode only.
- `generator/replay.py`: batch mode (24h, labels preserved) + live mode (asyncio, speed
  x1/x5/x20, on-demand inject, pause/reset).
- Generator tests.

## Phase 2 — Detection core
- `bus.py` (Redis Streams + in-memory fallback), `graph.py` (networkx MultiDiGraph,
  `neighborhood()`), `rules/engine.py` + `rules/rules.yaml` (R1–R11 + siloed variants),
  `fusion.py` (risk formula, entity-set incident correlation, 45m window, thresholds),
  `explain.py` (Jinja narratives, 4 templates), `store.py` (SQLite WAL).
- `tests/test_rules.py`, `tests/test_scenarios.py` green.

## Phase 3 — ML + benchmark
- `ml/features.py` (9-dim rolling 60m vectors, customer+staff), `ml/model.py`
  (IsolationForest trained on benign day at startup, persisted, 0–40 scaled, graceful
  degradation to 0).
- `bench/benchmark.py`: 24h batch, siloed vs fused, writes `deliverables/metrics.json` +
  `benchmark_report.md`. `tests/test_benchmark.py` green.

## Phase 4 — PQC + quantum
- `pqc.py`: ML-DSA-65 keypair at first boot, canonical-JSON → SHA-256 → sign, hash chain,
  verify; `quantum.py`: crypto inventory, HNDL scores, feeds R8.
- `POST /api/demo/tamper/{id}` support in store. `tests/test_pqc.py` green.

## Phase 5 — API + WS
- `api.py` (all REST routes per API_CONTRACT.md), `ws.py` (/ws/events throttled 30/s
  drop-oldest, /ws/alerts), `actions.py` (mock adapter, 300ms latency), `main.py`
  (single-process asyncio wiring), CORS for :3000.

## Phase 6 — Frontend
- Next.js 14 app router + TS + Tailwind + Recharts, dark SOC theme per spec tokens.
- Pages: `/` Live Ops, `/alerts`, `/alerts/[id]` (money screen), `/metrics`, `/quantum`.
- Demo dock on every page (start/pause/speed/inject/reset, hotkeys 1/2/3/space/r).
- Built in parallel by a subagent against API_CONTRACT.md; integrated + verified in
  browser against the live backend.

## Phase 7 — Deliverables + DoD sweep
- `make deliverables`: sample_data JSONL + labels, metrics.json, benchmark_report.md,
  DEMO_SCRIPT.md. README.md, ARCHITECTURE.md.
- Full Definition of Done checklist (section 11.4): docker compose up, demo flow, tests,
  no console errors, offline check. Polish pass on `/alerts/[id]`.
- Adversarial multi-agent review of the finished system; fix confirmed findings.

## Cut order (if needed, bottom-up)
graph API/viz → borderline variety (keep ≥10) → /quantum polish (keep data+R8) → ML layer
(keep ml_score field, 0) → metrics charts (keep big cards).
