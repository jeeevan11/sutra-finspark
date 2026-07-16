"""Rule engine. YAML carries config/docs; condition logic lives here keyed by rule id.

Two modes share one implementation:
- "fused"  : R1–R11, cross-domain context, feeds FusionEngine.
- "siloed" : naive single-signal variants (S*), per-domain, benchmark only.
"""

from __future__ import annotations

import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml

from ..config import IST
from ..generator.world import World, haversine_km, ALL_GEOS
from ..schemas import (AuthLogin, EdrAlert, Event, PayeeAdded, TlsSession, Txn,
                       VULNERABLE_KEX, inr)

RULES_PATH = Path(__file__).with_name("rules.yaml")


@dataclass
class Hit:
    rule_id: str
    name: str
    domain: str
    points: int
    detail: str
    ts: datetime
    entities: list[str]          # [0] is the hit's anchor entity
    event_ids: list[str]
    dedup_key: str


@dataclass
class _RuleCfg:
    id: str
    name: str
    domain: str
    points: int
    window_minutes: float
    params: dict = field(default_factory=dict)


def load_rule_configs() -> tuple[dict[str, _RuleCfg], dict[str, _RuleCfg]]:
    raw = yaml.safe_load(RULES_PATH.read_text())
    fused: dict[str, _RuleCfg] = {}
    for r in raw["rules"]:
        fused[r["id"]] = _RuleCfg(r["id"], r["name"], r["domain"], int(r["points"]),
                                  float(r.get("window_minutes", 0)), r.get("params", {}) or {})
    siloed: dict[str, _RuleCfg] = {}
    for v in raw.get("siloed_variants", []):
        base = fused.get(v.get("base", ""), None)
        params = dict(base.params) if base else {}
        params.update(v.get("params", {}) or {})
        siloed[v["id"]] = _RuleCfg(
            v["id"],
            v.get("name", base.name if base else v["id"]),
            v.get("domain", base.domain if base else "security"),
            int(v.get("points", base.points if base else 25)),
            float(v.get("window_minutes", base.window_minutes if base else 0)),
            params,
        )
    return fused, siloed


class RuleEngine:
    def __init__(self, world: World, mode: str = "fused") -> None:
        assert mode in ("fused", "siloed")
        self.world = world
        self.mode = mode
        fused, siloed = load_rule_configs()
        self.cfg = fused if mode == "fused" else siloed
        self._yaml_mtime = RULES_PATH.stat().st_mtime
        # --- detection state
        self._seen_dev: dict[str, set[str]] = {}
        self._seen_asn: dict[str, set[str]] = {}
        self._last_login: dict[str, tuple[datetime, str, str]] = {}
        self._r10_last: dict[str, datetime] = {}
        self._r2_recent: dict[str, tuple[datetime, str]] = {}
        self._failed_by_asn: dict[str, deque] = defaultdict(deque)   # (ts, eid, acct, cust)
        self._r1_last: dict[str, datetime] = {}
        self._r1_live: dict[str, Hit] = {}   # fired burst hits, detail kept fresh
        self._band_txns: dict[str, deque] = defaultdict(deque)       # acct -> (ts, eid, amount)
        self._r4_anchor: dict[str, str] = {}   # acct -> first event id of current run
        self._cust_txns: dict[str, deque] = defaultdict(deque)       # cust -> (ts, amount, eid)
        self._r5_last: dict[str, datetime] = {}
        self._edr: dict[str, deque] = defaultdict(deque)             # term -> (ts, eid, sev)
        self._egress: dict[str, deque] = defaultdict(deque)          # src -> (ts, bytes, eid)
        self._egress_level: dict[str, int] = defaultdict(int)
        self._egress_gen: dict[str, int] = defaultdict(int)
        self._woken: set[str] = set()

    # ------------------------------------------------------------------ config

    def maybe_reload(self) -> bool:
        """Hot-reload points/params when rules.yaml changes (live mode polls this)."""
        try:
            mtime = RULES_PATH.stat().st_mtime
        except OSError:
            return False
        if mtime == self._yaml_mtime:
            return False
        fused, siloed = load_rule_configs()
        self.cfg = fused if self.mode == "fused" else siloed
        self._yaml_mtime = mtime
        return True

    def _c(self, rule_id: str) -> Optional[_RuleCfg]:
        return self.cfg.get(rule_id)

    def _seen(self, customer_id: str) -> tuple[set[str], set[str]]:
        if customer_id not in self._seen_dev:
            cust = self.world.customers.get(customer_id)
            self._seen_dev[customer_id] = set(cust.devices) if cust else set()
            self._seen_asn[customer_id] = set(cust.asns) if cust else set()
        return self._seen_dev[customer_id], self._seen_asn[customer_id]

    # ------------------------------------------------------------------ observe

    def observe(self, ev: Event) -> list[Hit]:
        if isinstance(ev, AuthLogin):
            return self._on_login(ev)
        if isinstance(ev, Txn):
            return self._on_txn(ev)
        if isinstance(ev, PayeeAdded):
            return self._on_payee(ev)
        if isinstance(ev, EdrAlert):
            self._edr[ev.terminal_id].append((ev.ts, ev.event_id, ev.severity))
            return []
        if isinstance(ev, TlsSession):
            return self._on_tls(ev)
        return []

    # ------------------------------------------------------------------ logins

    def _on_login(self, ev: AuthLogin) -> list[Hit]:
        hits: list[Hit] = []
        if not ev.success:
            cfg = self._c("R1") or self._c("S1")
            if cfg:
                dq = self._failed_by_asn[ev.asn]
                dq.append((ev.ts, ev.event_id, ev.account_id, ev.customer_id))
                cutoff = ev.ts - timedelta(minutes=cfg.window_minutes)
                while dq and dq[0][0] < cutoff:
                    dq.popleft()
                threshold = int(cfg.params.get("threshold", 20))
                refire = timedelta(minutes=float(cfg.params.get("refire_minutes", 15)))
                last = self._r1_last.get(ev.asn)
                accts = sorted({a for _, _, a, _ in dq})
                custs = sorted({c for _, _, _, c in dq})
                detail = (f"{len(dq)} failed logins from {ev.asn} in "
                          f"{int(cfg.window_minutes)}m across {len(accts)} accounts")
                if len(dq) > threshold and (last is None or ev.ts - last > refire):
                    self._r1_last[ev.asn] = ev.ts
                    sample = int(cfg.params.get("evidence_sample", 8))
                    hit = Hit(
                        cfg.id, cfg.name, cfg.domain, cfg.points, detail,
                        ev.ts, [ev.asn] + accts + custs,
                        [eid for _, eid, _, _ in list(dq)[-sample:]],
                        f"{cfg.id}:{ev.asn}:{ev.event_id}",
                    )
                    self._r1_live[ev.asn] = hit
                    hits.append(hit)
                elif len(dq) > threshold and ev.asn in self._r1_live:
                    # burst still growing: keep the fired hit's story current so the
                    # narrative reports the full burst size, not the threshold crossing
                    self._r1_live[ev.asn].detail = detail
            return hits

        # successful login
        dev_seen, asn_seen = self._seen(ev.customer_id)
        new_dev, new_asn = ev.device_id not in dev_seen, ev.asn not in asn_seen

        if self.mode == "fused":
            cfg = self._c("R2")
            if cfg and new_dev and new_asn:
                self._r2_recent[ev.customer_id] = (ev.ts, ev.event_id)
                hits.append(Hit(
                    cfg.id, cfg.name, cfg.domain, cfg.points,
                    f"first sighting of BOTH device {ev.device_id} and network "
                    f"{ev.asn} ({ev.geo}) for {ev.customer_id}",
                    ev.ts, [ev.customer_id, ev.account_id, ev.device_id, ev.asn],
                    [ev.event_id], f"R2:{ev.event_id}",
                ))
        else:
            cfg = self._c("S2")
            if cfg and (new_dev or new_asn):
                what = "device" if new_dev else "network"
                which = ev.device_id if new_dev else ev.asn
                hits.append(Hit(
                    cfg.id, cfg.name, cfg.domain, cfg.points,
                    f"new {what} {which} for {ev.customer_id} (no baseline context)",
                    ev.ts, [ev.customer_id, ev.account_id, ev.device_id, ev.asn],
                    [ev.event_id], f"S2:{ev.event_id}",
                ))

        cfg = self._c("R10") or self._c("S10")
        prev = self._last_login.get(ev.customer_id)
        # device-novelty gate: a KNOWN handset appearing in a new city is roaming /
        # a SIM hop, not teleportation — the exculpatory half a siloed geo rule
        # cannot see. A takeover login (new device) still trips this.
        if cfg and prev and new_dev and ev.geo in ALL_GEOS and prev[1] in ALL_GEOS:
            dist = haversine_km(prev[1], ev.geo)
            hours = max((ev.ts - prev[0]).total_seconds(), 1.0) / 3600
            kmh = dist / hours
            refire = timedelta(minutes=float(cfg.params.get("refire_minutes", 60)))
            last_fire = self._r10_last.get(ev.customer_id)
            if dist > 50 and kmh > float(cfg.params.get("max_kmh", 900)) and (
                    last_fire is None or ev.ts - last_fire > refire):
                self._r10_last[ev.customer_id] = ev.ts
                hits.append(Hit(
                    cfg.id, cfg.name, cfg.domain, cfg.points,
                    f"{prev[1]} → {ev.geo} ({dist:,.0f} km) in {hours*60:.0f}m "
                    f"implies {kmh:,.0f} km/h",
                    ev.ts, [ev.customer_id, ev.account_id],
                    [prev[2], ev.event_id], f"{cfg.id}:{ev.event_id}",
                ))

        dev_seen.add(ev.device_id)
        asn_seen.add(ev.asn)
        self._last_login[ev.customer_id] = (ev.ts, ev.geo, ev.event_id)
        return hits

    # ------------------------------------------------------------------ payees

    def _on_payee(self, ev: PayeeAdded) -> list[Hit]:
        cfg = self._c("R3")
        if not cfg:
            return []
        recent = self._r2_recent.get(ev.customer_id)
        if recent and ev.ts - recent[0] <= timedelta(minutes=cfg.window_minutes):
            return [Hit(
                cfg.id, cfg.name, cfg.domain, cfg.points,
                f"payee {ev.payee_id} added {int((ev.ts - recent[0]).total_seconds() / 60)}m "
                f"after suspicious login on {ev.customer_id}",
                ev.ts, [ev.customer_id, ev.account_id, ev.payee_id, ev.device_id],
                [recent[1], ev.event_id], f"R3:{ev.event_id}",
            )]
        return []

    # ------------------------------------------------------------------ txns

    def _on_txn(self, ev: Txn) -> list[Hit]:
        hits: list[Hit] = []
        w = self.world

        cfg = self._c("R4") or self._c("S4")
        if cfg:
            lo = float(cfg.params.get("band_low", 45_000))
            hi = float(cfg.params.get("band_high", 50_000))
            if lo <= ev.amount < hi:
                dq = self._band_txns[ev.account_id]
                window = timedelta(minutes=cfg.window_minutes)
                # anchor the dedup key to the FIRST txn of a contiguous run — keying
                # on the sliding window's oldest entry would re-key (and re-score)
                # the same run as early txns age out
                if not dq or (ev.ts - dq[-1][0]) > window:
                    self._r4_anchor[ev.account_id] = ev.event_id
                dq.append((ev.ts, ev.event_id, ev.amount))
                cutoff = ev.ts - window
                while dq and dq[0][0] < cutoff:
                    dq.popleft()
                if len(dq) >= int(cfg.params.get("min_count", 3)):
                    span = int((dq[-1][0] - dq[0][0]).total_seconds() / 60)
                    hits.append(Hit(
                        cfg.id, cfg.name, cfg.domain, cfg.points,
                        f"{len(dq)} txns just under ₹50,000 on {ev.account_id} "
                        f"within {span}m (total {inr(sum(a for _, _, a in dq))})",
                        ev.ts, [ev.customer_id, ev.account_id, ev.payee_id],
                        [eid for _, eid, _ in dq],
                        f"{cfg.id}:{ev.account_id}:{self._r4_anchor[ev.account_id]}",
                    ))

        cfg = self._c("R5") or self._c("S5")
        if cfg:
            dq = self._cust_txns[ev.customer_id]
            dq.append((ev.ts, ev.amount, ev.event_id))
            cutoff = ev.ts - timedelta(minutes=cfg.window_minutes or 60)
            while dq and dq[0][0] < cutoff:
                dq.popleft()
            cust = w.customers.get(ev.customer_id)
            if cust:
                outflow = sum(a for _, a, _ in dq)
                mult = float(cfg.params.get("multiple", 3.0))
                refire = timedelta(minutes=float(cfg.params.get("refire_minutes", 60)))
                last = self._r5_last.get(ev.customer_id)
                if outflow > mult * cust.daily_outflow_mean and (
                        last is None or ev.ts - last > refire):
                    self._r5_last[ev.customer_id] = ev.ts
                    ratio = outflow / max(cust.daily_outflow_mean, 1)
                    hits.append(Hit(
                        cfg.id, cfg.name, cfg.domain, cfg.points,
                        f"1h outflow {inr(outflow)} is {ratio:.1f}× the 30-day daily "
                        f"average ({inr(cust.daily_outflow_mean)}) for {ev.customer_id}",
                        ev.ts, [ev.customer_id, ev.account_id],
                        [eid for _, _, eid in list(dq)[-10:]],
                        f"{cfg.id}:{ev.customer_id}:{ev.event_id}",
                    ))

        cfg = self._c("R6")
        if cfg and ev.terminal_id and ev.amount >= float(cfg.params.get("min_amount", 5e5)):
            dq = self._edr.get(ev.terminal_id)
            if dq:
                cutoff = ev.ts - timedelta(minutes=cfg.window_minutes)
                while dq and dq[0][0] < cutoff:
                    dq.popleft()
                if dq:
                    edr_ts, edr_eid, sev = dq[-1]
                    gap = int((ev.ts - edr_ts).total_seconds() / 60)
                    hits.append(Hit(
                        cfg.id, cfg.name, cfg.domain, cfg.points,
                        f"{inr(ev.amount)} {ev.txn_type} from {ev.terminal_id} "
                        f"{gap}m after a {sev}-severity EDR alert on the same terminal",
                        ev.ts, [ev.terminal_id, ev.staff_id or "", ev.account_id,
                                ev.customer_id],
                        [edr_eid, ev.event_id], f"R6:{ev.terminal_id}:{ev.event_id}",
                    ))

        cfg = self._c("R7") or self._c("S7")
        if cfg and ev.staff_id and ev.amount >= float(cfg.params.get("min_amount", 1e5)):
            staff = w.staff.get(ev.staff_id)
            if staff:
                t = ev.ts.astimezone(IST)
                h = t.hour + t.minute / 60
                lo, hi = staff.hours
                if h < lo or h >= hi:
                    hits.append(Hit(
                        cfg.id, cfg.name, cfg.domain, cfg.points,
                        f"{ev.staff_id} initiated {inr(ev.amount)} at {t.strftime('%H:%M')} IST, "
                        f"outside baseline hours "
                        f"({int(lo):02d}:{int(lo % 1 * 60):02d}–{int(hi):02d}:{int(hi % 1 * 60):02d})",
                        ev.ts, [ev.staff_id, ev.terminal_id or "", ev.account_id,
                                ev.customer_id],
                        [ev.event_id], f"{cfg.id}:{ev.event_id}",
                    ))

        cfg = self._c("R9") or self._c("S9")
        if cfg and ev.account_id in w.dormant_accounts and ev.account_id not in self._woken:
            self._woken.add(ev.account_id)
            hits.append(Hit(
                cfg.id, cfg.name, cfg.domain, cfg.points,
                f"{ev.account_id} dormant >90 days shows first activity: "
                f"{inr(ev.amount)} {ev.txn_type}",
                ev.ts, [ev.account_id, ev.customer_id],
                [ev.event_id], f"{cfg.id}:{ev.account_id}",
            ))

        cfg = self._c("R11") or self._c("S11")
        if cfg and not ev.payee_known and ev.amount >= float(cfg.params.get("min_amount", 1e6)):
            hits.append(Hit(
                cfg.id, cfg.name, cfg.domain, cfg.points,
                f"{inr(ev.amount)} {ev.txn_type} to never-paid payee {ev.payee_id}",
                ev.ts, [ev.customer_id, ev.account_id, ev.payee_id],
                [ev.event_id], f"{cfg.id}:{ev.event_id}",
            ))

        # clean anchor lists (staff/terminal may be empty strings)
        for h in hits:
            h.entities = [e for e in h.entities if e]
        return hits

    # ------------------------------------------------------------------ tls

    def _on_tls(self, ev: TlsSession) -> list[Hit]:
        cfg = self._c("R8")
        if not cfg:
            return []
        if ev.dst_known or ev.key_exchange not in VULNERABLE_KEX:
            return []
        dq = self._egress[ev.src]
        cutoff = ev.ts - timedelta(minutes=cfg.window_minutes)
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        if not dq and self._egress_level[ev.src]:
            # window drained — new generation, escalation restarts
            self._egress_gen[ev.src] += 1
            self._egress_level[ev.src] = 0
        dq.append((ev.ts, ev.bytes_out, ev.event_id))
        step = float(cfg.params.get("gb_step", 1e9))
        cum = sum(b for _, b, _ in dq)
        new_level = min(int(cum // step), int(cfg.params.get("max_levels", 8)))
        hits: list[Hit] = []
        gen = self._egress_gen[ev.src]
        for level in range(self._egress_level[ev.src] + 1, new_level + 1):
            hits.append(Hit(
                cfg.id, cfg.name, cfg.domain, cfg.points,
                f"cumulative vulnerable egress from {ev.src} crossed {level} GB in "
                f"{int(cfg.window_minutes)}m ({ev.key_exchange} to unknown {ev.dst_ip})",
                ev.ts, [ev.src, ev.dst_ip],
                [eid for _, _, eid in dq],
                f"R8:{ev.src}:g{gen}:L{level}",
            ))
        self._egress_level[ev.src] = max(self._egress_level[ev.src], new_level)
        return hits
