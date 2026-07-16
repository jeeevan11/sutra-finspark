// Types implemented verbatim from API_CONTRACT.md — do not edit without
// changing the contract and the backend together.

export type Severity = "medium" | "high" | "critical";
export type AlertStatus = "open" | "held" | "stepup" | "dismissed";
export type EventType =
  | "auth_login"
  | "edr_alert"
  | "tls_session"
  | "payee_added"
  | "password_reset"
  | "txn";
export type ActionType = "hold" | "stepup" | "dismiss";
export type EntityType =
  | "customer"
  | "staff"
  | "terminal"
  | "server"
  | "account"
  | "device"
  | "payee"
  | "asn"
  | "ip";
export type PqcReady = "green" | "amber" | "red";
export type Stream = "security" | "transaction";

export interface AlertSummary {
  alert_id: string; // "ALT-0001"
  created_ts: string;
  updated_ts: string;
  entity_type: string; // primary entity
  entity_id: string; // e.g. "CUST-0421"
  risk: number; // 0-100 int
  severity: Severity;
  status: AlertStatus;
  title: string; // "Account takeover with structuring — CUST-0421"
  scenario_guess: string; // "ato" | "terminal_compromise" | "quantum_exfil" | "generic"
  tags: string[]; // may include "quantum"
  evidence_count: number;
}

export interface EvidenceItem {
  event_id: string;
  ts: string;
  type: string; // event type; "action" for action records
  summary: string; // one-line human text
  entity_refs: string[]; // entity ids touched
  rule_ids: string[]; // rules this event contributed evidence to ([] for actions)
  detail: Record<string, unknown>; // raw event fields
}

export interface RuleHit {
  rule_id: string; // "R4"
  name: string; // "structuring"
  domain: "security" | "transaction" | "fused" | "quantum";
  points: number;
  detail: string; // "3 txns of ₹49,900 within 11m on ACC-9931-01"
  ts: string;
}

export interface ActionRecord {
  action: ActionType;
  ts: string;
  result: string; // "6 transactions held on ACC-9931-01"
}

export interface AlertDetail extends AlertSummary {
  narrative: string; // plain-English paragraph
  evidence: EvidenceItem[]; // time-ordered
  rule_hits: RuleHit[];
  ml_score: number; // 0-40
  signature: string; // hex, full ML-DSA-65 signature
  prev_hash: string; // hex sha256 of previous alert record ("GENESIS" for first)
  pubkey_fingerprint: string; // hex, 16 chars
  actions: ActionRecord[];
}

// --- REST responses ---

export interface HealthResponse {
  status: string;
  ts: string;
}

export interface AlertsResponse {
  alerts: AlertSummary[];
}

export interface ActionResponse {
  ok: boolean;
  alert_id: string;
  action: string;
  status: string;
  result: string;
}

export interface VerifyResponse {
  alert_id: string;
  signature_valid: boolean;
  chain_valid: boolean;
  algorithm: "ML-DSA-65";
  pubkey_fingerprint: string;
}

export interface ModeStats {
  total_alerts: number;
  true_positives: number; // alerts containing scenario events
  false_positives: number; // alerts on benign/borderline only
  precision: number; // 0-1
  recall: number; // 0-1 over the 3 scenarios
  detected_scenarios: string[]; // subset of ["A","B","C"]
}

export interface Metrics {
  generated_ts: string;
  seed: number;
  duration_hours: number;
  modes: {
    siloed: ModeStats;
    fused: ModeStats;
  };
  scenarios: {
    // keys "A" | "B" | "C"
    [k: string]: {
      name: string; // "Account takeover + structuring"
      fused: {
        detected: boolean;
        risk: number;
        time_to_detect_s: number | null;
      };
      siloed: {
        detected: boolean;
        max_score: number;
        alerts: number;
        note: string;
      };
    };
  };
  summary: {
    alert_reduction_pct: number; // e.g. 91.2
    fp_reduction_pct: number;
    analyst_hours_saved_per_day: number;
    rupees_at_risk_flagged: number; // total INR in scenario txns caught
  };
}

export interface QuantumAsset {
  asset_id: string; // "DB-2"
  kind: "server" | "terminal";
  sessions_by_kex: Record<string, number>; // keys: "RSA-2048"|"ECDHE-P256"|"X25519"|"X25519Kyber768-hybrid"
  pqc_ready: PqcReady;
  hndl_score: number; // 0-100
  bytes_to_unknown: number; // cumulative bytes to unknown destinations
  last_seen: string | null;
}

export interface QuantumResponse {
  assets: QuantumAsset[];
  hndl_incidents: AlertSummary[]; // alerts tagged "quantum"
}

export interface GraphResponse {
  nodes: Array<{ id: string; type: string }>;
  edges: Array<{
    src: string;
    dst: string;
    type: string;
    ts: string;
    event_id: string;
  }>;
}

export interface ReplayStatus {
  running: boolean;
  paused: boolean;
  speed: number;
  sim_time: string; // current simulated UTC time
  events_emitted: number;
  events_per_min: number; // wall-clock rate, smoothed
  open_alerts: { critical: number; high: number; medium: number };
  held_txns: number; // txns inside alerts currently in "held" status
  hndl_assets: number; // assets with pqc_ready == "red"
  seed: number;
}

export interface ReplayControlResponse {
  ok: boolean;
  status: ReplayStatus;
}

// --- WebSocket messages ---

export interface EventMessage {
  kind: "event";
  event_id: string;
  ts: string;
  type: string; // event type enum
  stream: Stream; // txn → transaction, all else → security
  summary: string; // preformatted mono-friendly line
  entity_refs: string[];
}

export interface AlertPushMessage {
  kind: "alert_created" | "alert_updated";
  alert: AlertSummary;
}

export type Scenario = "A" | "B" | "C";
export type ReplaySpeed = 1 | 5 | 20;
