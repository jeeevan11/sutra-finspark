"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSutra } from "./SutraProvider";

const LINKS = [
  { href: "/overview", label: "Overview" },
  { href: "/", label: "Live Ops" },
  { href: "/alerts", label: "Alerts" },
  { href: "/metrics", label: "Metrics" },
  { href: "/quantum", label: "Quantum" },
];

export function Nav() {
  const pathname = usePathname();
  const { status, backendUp, alertsWsStatus } = useSutra();

  const live = backendUp && status !== null && status.running && !status.paused;
  const paused = backendUp && status !== null && status.running && status.paused;

  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-night/95 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-[1700px] items-center gap-8 px-5">
        <Link href="/" className="flex items-baseline gap-3">
          <span className="text-xl font-bold tracking-[0.22em] text-body">
            SUTRA
          </span>
          <span className="hidden text-[11px] uppercase tracking-wider text-muted lg:inline">
            Security Unified Telemetry &amp; Risk Analytics
          </span>
        </Link>

        <nav className="flex items-center gap-1 text-sm">
          {LINKS.map((l) => {
            const active =
              l.href === "/"
                ? pathname === "/"
                : pathname === l.href || pathname.startsWith(`${l.href}/`);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded px-3 py-1.5 transition-colors ${
                  active
                    ? "bg-panel text-accent"
                    : "text-body/80 hover:bg-panel hover:text-body"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-5">
          {/* Replay live/paused indicator */}
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider">
            {live ? (
              <>
                <span className="live-pulse h-2.5 w-2.5 rounded-full bg-ok" />
                <span className="text-ok">Live ×{status?.speed}</span>
              </>
            ) : paused ? (
              <>
                <span className="h-2.5 w-2.5 rounded-full bg-high" />
                <span className="text-high">Paused</span>
              </>
            ) : (
              <>
                <span className="h-2.5 w-2.5 rounded-full bg-muted/60" />
                <span className="text-muted">
                  {backendUp ? "Idle" : "Offline"}
                </span>
              </>
            )}
          </div>

          {/* WS connection indicator */}
          <div
            className="flex items-center gap-1.5"
            title={`Alert stream: ${alertsWsStatus}`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                alertsWsStatus === "open" ? "bg-ok" : "bg-high"
              }`}
            />
            <span className="font-mono text-[10px] uppercase text-muted">
              ws
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
