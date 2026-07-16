# SUTRA — conventions for Claude Code sessions

Security Unified Telemetry & Risk Analytics: hackathon prototype (FinSpark'26 PS2, Bank of
Maharashtra). Fuses security telemetry + core-banking transactions into one entity graph,
scores risk (rules + IsolationForest), emits explainable, ML-DSA-65-signed alerts.

## Stack
- Backend: Python 3.11 (Docker) / 3.13 (local venv), FastAPI + uvicorn, pydantic v2,
  SQLAlchemy + SQLite (WAL), redis-py async, networkx, scikit-learn, Jinja2, PyYAML,
  dilithium-py (ML-DSA-65).
- Frontend: Next.js 14 app router, TypeScript, Tailwind, Recharts, native WebSocket.
- Bus: Redis Streams (group `sutra-core`) in docker/live; `SUTRA_BUS=memory` fallback;
  batch/benchmark feeds fusion directly (no bus).

## Commands (make is law — run from repo root)
- `make test` — pytest (backend/tests), no Redis/Docker needed.
- `make bench` — siloed-vs-fused 24h benchmark → deliverables/metrics.json + report.
- `make up` / `docker compose up` — full stack (redis, backend:8000, frontend:3000).
- `make demo` — starts the live replay via API (after `make up`).
- `make deliverables` — regenerates everything under deliverables/.
- Local dev: `make dev-backend` (uvicorn :8000, memory bus), `make dev-frontend` (next dev :3000).
- Python venv: `backend/.venv` — activate or use `backend/.venv/bin/python`.

## Hard rules
- Determinism: ALL randomness flows from `SUTRA_SEED` (default 42) through explicit
  `random.Random`/`numpy` generators — never module-level `random`. Same seed ⇒ same
  replay ⇒ same alerts.
- Zero runtime network egress: no external APIs, no CDNs, no telemetry. Build-time
  pip/npm only.
- Synthetic data only, obviously fake IDs (CUST-0421, ACC-9931-01). INR amounts, UTC
  internal timestamps, IST (Asia/Kolkata) display.
- Reliability beats elegance beats features. No speculative abstractions, no auth.

## Structure
- backend/sutra/: config, schemas, generator/{world,noise,scenarios,replay}, bus, graph,
  rules/{engine,rules.yaml}, ml/{features,model}, fusion, explain, pqc, quantum, actions,
  store, api, ws, main.
- backend/bench/benchmark.py, backend/tests/.
- frontend/: Next.js app (see API_CONTRACT.md for the exact REST/WS shapes it consumes).
- deliverables/: generated artifacts (metrics.json, sample_data/, DEMO_SCRIPT.md, report).

## Conventions
- Record every non-obvious decision as one line in DECISIONS.md.
- Commit at phase boundaries: `phase N: <summary>`.
- API shapes are pinned in API_CONTRACT.md — change it and both sides together, never one.
- Risk formula: `min(100, round(0.65·Σ rule_points + 0.35·(ml_score·2.5)))`; alert at ≥60;
  severity 60–74 medium / 75–89 high / 90+ critical; incident window 45 min.
