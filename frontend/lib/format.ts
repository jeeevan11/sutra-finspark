// INR / IST formatting helpers. All display is Indian-formatted:
// ₹ with Indian digit grouping, timestamps in Asia/Kolkata.

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const inrCompactSafe = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 0,
});

/** ₹18,50,000 — Indian digit grouping. */
export function formatINR(amount: number): string {
  if (!Number.isFinite(amount)) return "₹—";
  return inrFormatter.format(amount);
}

/** 18,50,000 (no rupee sign) — Indian digit grouping. */
export function formatIndianNumber(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return inrCompactSafe.format(n);
}

const istTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const istDateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

/** HH:mm:ss in IST (Asia/Kolkata). Returns "—" for invalid input. */
export function formatIST(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return istTime.format(d);
}

/** "16 Jul, 14:32:05" in IST — for headers where the date matters. */
export function formatISTFull(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return istDateTime.format(d);
}

/**
 * Relative age like "42s", "3m", "5h", "2d".
 * Alert timestamps live on the backend's SIMULATED clock, so pass the current
 * sim time (epoch ms, from ReplayStatus.sim_time) as `nowMs`; falls back to
 * wall clock only when replay status is unavailable. Negative ages clamp to "0s".
 */
export function relativeAge(
  ts: string | null | undefined,
  nowMs?: number | null,
): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  const now =
    nowMs !== undefined && nowMs !== null && Number.isFinite(nowMs)
      ? nowMs
      : Date.now();
  const s = Math.max(0, Math.floor((now - d.getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

/** Human bytes: 1.4 GB / 320 MB / 12 KB. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

/** Seconds → "38s" | "4m 12s". */
export function formatSeconds(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

/** 0.914 → "91.4%" */
export function formatPct01(x: number): string {
  if (!Number.isFinite(x)) return "—";
  return `${(x * 100).toFixed(1)}%`;
}
