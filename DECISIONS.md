# DECISIONS

One line per non-obvious decision, newest at the bottom.

- Repo root is the opened workspace directory itself (it was empty); no extra `sutra/` nesting — quickstart paths stay one level shallower.
- Python deps via `requirements.txt` (not pyproject): simplest thing that Docker + venv both consume.
- Local dev runs Python 3.13 (machine default); Docker image pins 3.11 per spec — code targets 3.11+ stdlib only.
- `bus.py` supports Redis Streams (docker/live) AND an in-process asyncio queue (`SUTRA_BUS=memory`) so `make test`/`make bench` need no Redis; batch/benchmark mode bypasses the bus entirely and feeds fusion directly (determinism + speed).
- Rule hits are deduped per (rule_id, dedup_key) within an incident; R8 is the one *escalating* rule — it re-fires at each whole GB of vulnerable egress crossed (each GB is a new violation), which is what lets Scenario C reach risk ≥ 80 under the pinned 0.65/0.35 formula.
- Incidents are entity-*set* scoped (connected via shared entities), not single-entity: a credential-stuffing burst + the ATO on one victim merge into ONE alert; primary entity = most points, tie-broken customer > staff > terminal > server > account > device > payee > asn > ip.
- Scenario B debits a dormant business account (spec leaves the account unspecified): adds R9+R5+R11 to R6+R7 so rules alone carry B past risk 85 even if ML degrades; story stays "compromised terminal drains dormant corporate account".
- ML score is only computed when an incident has ≥25 rule points (ML alone can never fire an alert: 0.35×100 = 35 < 60); keeps the benign day fast and FP-proof by construction.
- Servers get no IsolationForest score (features are customer/staff-shaped); quantum alerts ride on rule points alone.
- Siloed mode = security+transaction domains only (no quantum monitoring — models today's SIEM+FRM world, so Scenario C is missed), with naive rule variants (S2 device-OR-asn, S5 velocity 2×, S7 flat off-hours) defined alongside R1–R11 in rules.yaml.
- Benign generator explicitly avoids the ₹44k–50k structuring band and never sends ≥₹10L to unknown payees: synthetic data tuned so the fused false-positive rate is provably zero on the benign day (stated honestly in benchmark_report.md).
- Narratives are Jinja templates (4: ato / terminal / quantum / generic), never an LLM — deterministic, offline, hallucination-proof (trust decision recorded in ARCHITECTURE.md).
- Events live in in-memory ring buffers; only alerts/actions are persisted to SQLite (alerts embed their evidence copies, so the signed record is self-contained).
- Frontend calls the backend directly at NEXT_PUBLIC_API_BASE (default http://localhost:8000) with CORS enabled, rather than proxying through Next — fewer moving parts on the projector.
- Live injections compress intra-scenario gaps 0.5× (spec 6.4 allows it) so Scenario A's critical alert lands ~7s after pressing 1 at ×20; batch mode keeps the exact spec offsets for the benchmark.
- Compose healthcheck probes 127.0.0.1, not localhost: busybox wget tries ::1 first and the Next standalone server binds IPv4 only — the frontend container showed (unhealthy) forever while serving fine.
- Entity-graph view on alert detail is a hand-rolled deterministic radial SVG, not Cytoscape (spec stretch suggested it): the 1-hop payload is ~a dozen nodes, a fixed sorted-circle layout renders identically every run, and zero new npm deps keeps the offline bundle small.
- MITRE ATT&CK tags per dominant pattern (ato → T1110.004/T1078, terminal → T1071.001/T1657, quantum → T1048.002) ride in the existing alert tags list — techniques the evidence actually demonstrates, nothing aspirational.
- /overview cover page cancels the root layout's pb-40 dock clearance and hides the floating dock on that route only — it must fit exactly one viewport for screenshots; its START DEMO CTA replaces the dock there (hotkeys stay live).
- Adversarial-review fixes (all six confirmed findings): inject uses ensure_running() so it never clears an operator pause; chain verification checks every record's ML-DSA signature (an unkeyed hash can be recomputed by a tamperer, even on the tail); pubkey_fingerprint is signed into the payload and verify reports the record's fingerprint; R4's dedup key anchors to the first txn of a contiguous run (sliding-window anchor re-scored long runs); R10 requires device novelty (a known handset in a new city is roaming, not teleportation — and the takeover login still trips it); merging two already-alerted incidents retires the absorbed alert as dismissed "[Merged into ALT-X]" instead of orphaning it open.
