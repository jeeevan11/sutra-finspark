# SUTRA API Contract (pinned — backend and frontend both implement THIS)

Base URL (browser-visible): `NEXT_PUBLIC_API_BASE`, default `http://localhost:8000`.
All REST routes are under `/api`. All timestamps are ISO-8601 UTC strings
(`2026-07-16T09:15:00+00:00`); the frontend renders them in IST (Asia/Kolkata).
Amounts are INR numbers (float rupees).

## Enums

- `severity`: `"medium"` (risk 60–74) | `"high"` (75–89) | `"critical"` (90+)
- `alert status`: `"open" | "held" | "stepup" | "dismissed"`
- `event type`: `"auth_login" | "edr_alert" | "tls_session" | "payee_added" | "password_reset" | "txn"`
- `action`: `"hold" | "stepup" | "dismiss"`
- `entity_type`: `"customer" | "staff" | "terminal" | "server" | "account" | "device" | "payee" | "asn" | "ip"`
- `pqc_ready` badge: `"green" | "amber" | "red"`
- `stream` (WS events): `"security" | "transaction"`

## Shared shapes

```ts
interface AlertSummary {
  alert_id: string;            // "ALT-0001"
  created_ts: string;
  updated_ts: string;
  entity_type: string;         // primary entity
  entity_id: string;           // e.g. "CUST-0421"
  risk: number;                // 0-100 int
  severity: "medium" | "high" | "critical";
  status: "open" | "held" | "stepup" | "dismissed";
  title: string;               // "Account takeover with structuring — CUST-0421"
  scenario_guess: string;      // "ato" | "terminal_compromise" | "quantum_exfil" | "generic"
  tags: string[];              // may include "quantum"
  evidence_count: number;
}

interface EvidenceItem {
  event_id: string;
  ts: string;
  type: string;                // event type; "action" for action records
  summary: string;             // one-line human text, e.g. "UPI ₹49,900 ACC-9931-01 → PAYEE-NEW-01"
  entity_refs: string[];       // entity ids touched
  rule_ids: string[];          // rules this event contributed evidence to ([] for actions)
  detail: Record<string, unknown>;  // raw event fields
}

interface RuleHit {
  rule_id: string;             // "R4"
  name: string;                // "structuring"
  domain: "security" | "transaction" | "fused" | "quantum";
  points: number;
  detail: string;              // "3 txns of ₹49,900 within 11m on ACC-9931-01"
  ts: string;
}

interface ActionRecord {
  action: "hold" | "stepup" | "dismiss";
  ts: string;
  result: string;              // "6 transactions held on ACC-9931-01"
}

interface AlertDetail extends AlertSummary {
  narrative: string;           // plain-English paragraph
  evidence: EvidenceItem[];    // time-ordered
  rule_hits: RuleHit[];
  ml_score: number;            // 0-40
  signature: string;           // hex, full ML-DSA-65 signature
  prev_hash: string;           // hex sha256 of previous alert record ("GENESIS" for first)
  pubkey_fingerprint: string;  // hex, 16 chars
  actions: ActionRecord[];
}
```

## REST

### `GET /api/health`
→ `{ "status": "ok", "ts": string }`

### `GET /api/alerts?status=<status>&severity=<severity>`
Both filters optional. → `{ "alerts": AlertSummary[] }` sorted risk desc, then updated_ts desc.

### `GET /api/alerts/{alert_id}`
→ `AlertDetail`. 404 `{ "detail": "..." }` if unknown.

### `POST /api/alerts/{alert_id}/action`  body `{ "action": "hold" | "stepup" | "dismiss" }`
Simulated core-banking latency ~300ms.
→ `{ "ok": true, "alert_id": string, "action": string, "status": string, "result": string }`

### `GET /api/alerts/{alert_id}/verify`
→ `{ "alert_id": string, "signature_valid": boolean, "chain_valid": boolean,
     "algorithm": "ML-DSA-65", "pubkey_fingerprint": string }`

### `POST /api/demo/tamper/{alert_id}`
Mutates the stored record directly (demo of tamper evidence).
→ `{ "ok": true, "alert_id": string, "mutated": string }`

### `GET /api/metrics`
Serves `deliverables/metrics.json` if present, else computes an in-memory summary of the
same shape:
```ts
interface Metrics {
  generated_ts: string;
  seed: number;
  duration_hours: number;
  modes: {
    siloed: ModeStats;
    fused: ModeStats;
  };
  scenarios: {                       // keys "A" | "B" | "C"
    [k: string]: {
      name: string;                  // "Account takeover + structuring"
      fused: { detected: boolean; risk: number; time_to_detect_s: number | null };
      siloed: { detected: boolean; max_score: number; alerts: number; note: string };
    };
  };
  summary: {
    alert_reduction_pct: number;     // e.g. 91.2
    fp_reduction_pct: number;
    analyst_hours_saved_per_day: number;
    rupees_at_risk_flagged: number;  // total INR in scenario txns caught
  };
  _bench_wall_seconds?: {            // internal timing (underscore = non-contract), ignore
    fused: number; siloed: number; events: number;
  };
}
interface ModeStats {
  total_alerts: number;
  true_positives: number;            // alerts containing scenario events
  false_positives: number;           // alerts on benign/borderline only
  precision: number;                 // 0-1
  recall: number;                    // 0-1 over the 3 scenarios
  detected_scenarios: string[];      // subset of ["A","B","C"]
}
```

### `GET /api/quantum`
```ts
{
  assets: Array<{
    asset_id: string;                       // "DB-2"
    kind: "server" | "terminal";
    sessions_by_kex: Record<string, number>; // keys: "RSA-2048"|"ECDHE-P256"|"X25519"|"X25519Kyber768-hybrid"
    pqc_ready: "green" | "amber" | "red";
    hndl_score: number;                     // 0-100
    bytes_to_unknown: number;               // cumulative bytes to unknown destinations
    last_seen: string | null;
  }>;
  hndl_incidents: AlertSummary[];           // alerts tagged "quantum"
}
```

### `GET /api/graph/{entity_id}`
→ `{ "nodes": [{ "id": string, "type": string }], "edges": [{ "src": string, "dst": string, "type": string, "ts": string, "event_id": string }] }`
(1-hop neighborhood; 404 if entity unknown.)

### Replay control
- `POST /api/replay/start` body `{ "speed": 1 | 5 | 20 }` (speed optional, default 20)
- `POST /api/replay/pause`   (toggles pause/resume)
- `POST /api/replay/reset`   (wipes alerts + graph, restarts world from seed)
- `POST /api/replay/inject/{A|B|C}`
- All → `{ "ok": true, "status": ReplayStatus }`
- `GET /api/replay/status` → `ReplayStatus`

```ts
interface ReplayStatus {
  running: boolean;
  paused: boolean;
  speed: number;
  sim_time: string;              // current simulated UTC time
  events_emitted: number;
  events_per_min: number;        // wall-clock rate, smoothed
  open_alerts: { critical: number; high: number; medium: number };
  held_txns: number;             // txns inside alerts currently in "held" status
  hndl_assets: number;           // assets with pqc_ready == "red"
  seed: number;
}
```

## WebSockets

### `WS /ws/events` — live event river. Throttled ~30 msg/s, drop-oldest.
Each message:
```ts
{
  kind: "event";
  event_id: string;
  ts: string;
  type: string;              // event type enum
  stream: "security" | "transaction";   // txn → transaction, all else → security
  summary: string;           // preformatted mono-friendly line
  entity_refs: string[];
}
```

### `WS /ws/alerts` — alert lifecycle pushes.
```ts
{ kind: "alert_created" | "alert_updated"; alert: AlertSummary }
```
Status changes from actions also arrive as `alert_updated`.

## CORS
Backend allows origins `http://localhost:3000` and `http://127.0.0.1:3000`.
