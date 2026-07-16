"use client";

import type { Severity } from "@/lib/types";
import { severityColor } from "./ui";

/**
 * Simple SVG semicircular gauge, 0-100, colored by severity.
 * Track = border color; value arc = severity color; big mono number inside.
 */
export function RiskGauge({
  risk,
  severity,
}: {
  risk: number;
  severity: Severity;
}) {
  const r = 50;
  const arcLen = Math.PI * r; // semicircle length
  const frac = Math.max(0, Math.min(100, risk)) / 100;
  const color = severityColor(severity);

  return (
    <svg viewBox="0 0 120 72" className="w-[160px]" role="img" aria-label={`Risk ${risk} of 100`}>
      <path
        d="M 10 62 A 50 50 0 0 1 110 62"
        fill="none"
        stroke="var(--edge)"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <path
        d="M 10 62 A 50 50 0 0 1 110 62"
        fill="none"
        stroke={color}
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={`${frac * arcLen} ${arcLen}`}
      />
      <text
        x="60"
        y="52"
        textAnchor="middle"
        fill={color}
        fontSize="30"
        fontWeight="700"
        fontFamily="var(--font-jetbrains), ui-monospace, monospace"
      >
        {Math.round(risk)}
      </text>
      <text
        x="60"
        y="68"
        textAnchor="middle"
        fill="var(--muted)"
        fontSize="9"
        letterSpacing="2"
        fontFamily="var(--font-inter), system-ui, sans-serif"
      >
        RISK / 100
      </text>
    </svg>
  );
}
