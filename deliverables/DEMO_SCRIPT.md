# SUTRA — 3-minute demo script

**Recording:** OBS Studio, 1080p60, capture the browser at `http://localhost:3000`,
mic on, **single take at ×20 speed**. Full-screen the browser (hide the tab bar).
Before recording: `docker compose up` (wait for all three healthchecks green),
confirm the demo dock reads `stopped · 20:30:00 IST`. Keep a terminal on a second
monitor only for the tamper `curl` (step 8) — everything else is driven from the
on-screen demo dock (bottom-right) with keyboard shortcuts.

Shortcuts: `1`/`2`/`3` inject A/B/C · `space` pause/resume · `r` (twice) reset.

---

### 0:00 — Open (Live Ops, `/`)
> "This is SUTRA — one correlation layer over a bank's security telemetry *and* its
> core-banking transactions. Today those run as two silos: a SOC and a fraud team,
> each seeing half the story."

Press **Start** (or the dock's ▶). Two event rivers begin flowing — logins, EDR,
TLS on the left; UPI/IMPS/NEFT/RTGS on the right. KPI strip live.
> "Everything you see is synthetic, seeded, fully offline. Let it run — this is a
> calm night. No alerts, because nothing correlates."

**Let noise run ~20 seconds.** Open-alerts stay 0/0/0.

### 0:25 — Scenario A: account takeover + structuring
Press **`1`**.
> "Now a credential-stuffing burst from a hostile network in Bucharest — forty
> failed logins across fifteen accounts. One succeeds, on a customer's account,
> from a brand-new device. A never-seen payee is added, then three UPI transfers of
> ₹49,900 — deliberately under the ₹50,000 reporting line. That's structuring."

Within ~15s a **critical** alert appears in the right feed. Click it.

### 0:45 — The money screen (`/alerts/ALT-0001`)
> "One alert, not forty. Risk 100. Here's the plain-English narrative — generated
> from templates, not an LLM, so it can't hallucinate and runs air-gapped."

Point to the **evidence chain** (≥6 events, rule chips), then the **rule-hit
breakdown** (R1 burst, R2 new device+network, R3 payee, R4 structuring, R5
velocity) and the **ML anomaly +40/40**.
> "Six rules plus the ML anomaly layer, every contributing event on one timeline."

Click **Hold transactions**. Button confirms ✓, status → HELD.
> "One click reaches the mock core-banking adapter and holds the outgoing transfers."

### 1:20 — Scenario B: compromised branch terminal
Press **`2`**, return to Live Ops or the alert feed, open the new alert.
> "Different attack. A branch terminal throws an EDR alert. Seven minutes later that
> *same* terminal pushes an ₹18,50,000 RTGS out of a dormant corporate account, at
> 22:40, well outside the teller's hours. Alone, each signal is low-risk — the EDR
> team and the fraud team would each shrug. Correlated, it's a compromised terminal.
> Risk 100."

### 1:45 — The proof: fused vs siloed (`/metrics`)
Click **Metrics**.
> "We benchmarked SUTRA against a simulated legacy stack on the same 24-hour day.
> Siloed: 35 alerts, 30 of them false positives, precision 0.14. SUTRA: 3 alerts,
> zero false positives, precision 1.0 — a **91% cut in alert volume**, every real
> attack caught. That's roughly ten analyst-hours saved a day, and ₹20 lakh of
> attack outflow flagged before settlement."

### 2:05 — Scenario C: the quantum angle (`/quantum`)
Press **`3`**, click **Quantum**.
> "Third attack: a database is exfiltrating 4.2 GB to an unknown host over
> RSA-2048 — classical crypto. Harvest-now-decrypt-later: steal it today, decrypt it
> when a quantum computer arrives. DB-2 goes red, HNDL score 100. No fraud or SIEM
> tool watches for this today. SUTRA does."

### 2:25 — Tamper-evidence (back to the alert)
Open the Scenario A alert. Click **Verify**.
> "Every alert is signed with ML-DSA-65 — a NIST post-quantum signature — and
> hash-chained. Verify: signature valid, chain valid."

On the terminal, run:
```
curl -X POST http://localhost:8000/api/demo/tamper/ALT-0001
```
> "Now an insider quietly edits the amount in the database."

Click **Verify** again → **TAMPERED ✗**.
> "The tamper is caught instantly. A regulator-grade, quantum-safe audit trail."

### 2:45 — Close (PS2 checklist)
> "So — SUTRA correlates cyber telemetry with transactions, detects threats
> proactively, spots fraud patterns, flags quantum attack indicators, cuts false
> positives by design, and explains every call. On-prem, open-source, one
> `docker compose up`, zero data leaves the bank. That's the missing correlation
> layer. Thank you."

Press **`r`** twice to reset for the next run.

---

**Timing cushions:** at ×20 a scenario fully lands in ~15–20s wall-clock. If an
alert is slow, keep narrating the rivers — never dead-air waiting. If you must
re-run, `r r` resets to a pristine seeded world (identical every time).
