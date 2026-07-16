"use client";

import type { AlertStatus, PqcReady, Severity } from "@/lib/types";

export const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "#EF4444",
  high: "#F59E0B",
  medium: "#FBBF24",
};

export function severityColor(sev: Severity): string {
  return SEVERITY_COLOR[sev] ?? "#FBBF24";
}

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-edge bg-panel ${className}`}
    >
      {(title || right) && (
        <div className="flex items-center justify-between border-b border-edge px-4 py-2.5">
          <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
            {title}
          </h2>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function SeverityDot({ severity }: { severity: Severity }) {
  return (
    <span
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: severityColor(severity) }}
      title={severity}
    />
  );
}

export function SeverityChip({ severity }: { severity: Severity }) {
  const c = severityColor(severity);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider"
      style={{ borderColor: `${c}66`, color: c, backgroundColor: `${c}14` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: c }} />
      {severity}
    </span>
  );
}

const STATUS_STYLE: Record<AlertStatus, { label: string; cls: string }> = {
  open: { label: "OPEN", cls: "border-accent/50 text-accent bg-accent/10" },
  held: { label: "HELD", cls: "border-critical/50 text-critical bg-critical/10" },
  stepup: { label: "STEP-UP", cls: "border-high/50 text-high bg-high/10" },
  dismissed: { label: "DISMISSED", cls: "border-edge text-muted bg-transparent" },
};

export function StatusPill({ status }: { status: AlertStatus }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.open;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium tracking-wide ${s.cls}`}
    >
      {s.label}
    </span>
  );
}

const TYPE_STYLE: Record<string, string> = {
  auth_login: "text-accent border-accent/40",
  edr_alert: "text-critical border-critical/40",
  tls_session: "text-ok border-ok/40",
  payee_added: "text-high border-high/40",
  password_reset: "text-high border-high/40",
  txn: "text-medium border-medium/40",
  action: "text-accent border-accent/60",
};

const TYPE_LABEL: Record<string, string> = {
  auth_login: "AUTH",
  edr_alert: "EDR",
  tls_session: "TLS",
  payee_added: "PAYEE",
  password_reset: "PWDRST",
  txn: "TXN",
  action: "ACTION",
};

export function TypeBadge({ type }: { type: string }) {
  const cls = TYPE_STYLE[type] ?? "text-muted border-edge";
  const label = TYPE_LABEL[type] ?? type.toUpperCase().slice(0, 7);
  return (
    <span
      className={`inline-flex w-[62px] shrink-0 items-center justify-center rounded border px-1 py-px font-mono text-[10px] font-medium ${cls}`}
    >
      {label}
    </span>
  );
}

const PQC_STYLE: Record<PqcReady, { label: string; cls: string }> = {
  green: { label: "PQC-READY", cls: "border-ok/50 text-ok bg-ok/10" },
  amber: { label: "PARTIAL", cls: "border-high/50 text-high bg-high/10" },
  red: { label: "VULNERABLE", cls: "border-critical/50 text-critical bg-critical/10" },
};

export function PqcReadyBadge({ ready }: { ready: PqcReady }) {
  const s = PQC_STYLE[ready] ?? PQC_STYLE.amber;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[11px] ${s.cls}`}
    >
      {s.label}
    </span>
  );
}

/** Muted "backend down" placeholder used across pages. */
export function WaitingForBackend({ label }: { label?: string }) {
  return (
    <div className="flex h-full min-h-[80px] items-center justify-center p-6 text-sm text-muted">
      {label ?? "waiting for backend…"}
    </div>
  );
}
