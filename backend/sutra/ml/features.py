"""Per-entity sliding-window (60m) feature vectors for the anomaly model.

9 dims, shared shape for customers and staff:
  0 failed_login_count   1 new_device_count      2 distinct_asns
  3 txn_count            4 outflow_z (vs baseline) 5 max_txn_z
  6 unknown_payee_share  7 hour_deviation (IST)   8 payee_add_count
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from datetime import datetime, timedelta

from ..config import IST
from ..generator.world import World
from ..schemas import AuthLogin, Event, PayeeAdded, Txn

WINDOW = timedelta(minutes=60)
N_FEATURES = 9


def _prune(dq: deque, cutoff: datetime) -> None:
    while dq and dq[0][0] < cutoff:
        dq.popleft()


class FeatureTracker:
    def __init__(self, world: World) -> None:
        self.world = world
        self._fails: dict[str, deque] = defaultdict(deque)        # (ts,)
        self._new_devs: dict[str, deque] = defaultdict(deque)     # (ts,)
        self._asns: dict[str, deque] = defaultdict(deque)         # (ts, asn)
        self._txns: dict[str, deque] = defaultdict(deque)         # (ts, amount, known)
        self._payee_adds: dict[str, deque] = defaultdict(deque)   # (ts,)
        self._staff_txns: dict[str, deque] = defaultdict(deque)   # (ts, amount, known)
        self._dev_seen: dict[str, set[str]] = {}

    def _devices(self, customer_id: str) -> set[str]:
        if customer_id not in self._dev_seen:
            cust = self.world.customers.get(customer_id)
            self._dev_seen[customer_id] = set(cust.devices) if cust else set()
        return self._dev_seen[customer_id]

    def observe(self, ev: Event) -> None:
        if isinstance(ev, AuthLogin):
            if ev.success:
                seen = self._devices(ev.customer_id)
                if ev.device_id not in seen:
                    seen.add(ev.device_id)
                    self._new_devs[ev.customer_id].append((ev.ts,))
                self._asns[ev.customer_id].append((ev.ts, ev.asn))
            else:
                self._fails[ev.customer_id].append((ev.ts,))
        elif isinstance(ev, Txn):
            self._txns[ev.customer_id].append((ev.ts, ev.amount, ev.payee_known))
            if ev.staff_id:
                self._staff_txns[ev.staff_id].append((ev.ts, ev.amount, ev.payee_known))
        elif isinstance(ev, PayeeAdded):
            self._payee_adds[ev.customer_id].append((ev.ts,))

    # ------------------------------------------------------------------ vectors

    def vector(self, entity_id: str, now: datetime) -> list[float]:
        if entity_id.startswith("STAFF-"):
            return self._staff_vector(entity_id, now)
        return self._customer_vector(entity_id, now)

    def _hour_dev(self, now: datetime, lo: float, hi: float) -> float:
        h = now.astimezone(IST).hour + now.astimezone(IST).minute / 60
        return max(lo - h, h - hi, 0.0)

    def _customer_vector(self, cid: str, now: datetime) -> list[float]:
        cutoff = now - WINDOW
        for dq in (self._fails[cid], self._new_devs[cid], self._asns[cid],
                   self._txns[cid], self._payee_adds[cid]):
            _prune(dq, cutoff)
        cust = self.world.customers.get(cid)
        txns = self._txns[cid]
        outflow = sum(a for _, a, _ in txns)
        max_amt = max((a for _, a, _ in txns), default=0.0)
        unknown = sum(1 for _, _, k in txns if not k)
        if cust:
            hourly_mean = cust.daily_outflow_mean / 12
            hourly_std = cust.daily_outflow_std / math.sqrt(12) + 1
            typ_txn = cust.daily_outflow_mean / 8 + 1
            lo, hi = cust.active_hours
        else:
            hourly_mean, hourly_std, typ_txn, (lo, hi) = 1000.0, 1000.0, 1000.0, (8, 22)
        return [
            float(len(self._fails[cid])),
            float(len(self._new_devs[cid])),
            float(len({a for _, a in self._asns[cid]})),
            float(len(txns)),
            max(-3.0, min(60.0, (outflow - hourly_mean) / hourly_std)),
            max(0.0, min(60.0, max_amt / typ_txn)),
            unknown / len(txns) if txns else 0.0,
            self._hour_dev(now, lo, hi),
            float(len(self._payee_adds[cid])),
        ]

    def _staff_vector(self, sid: str, now: datetime) -> list[float]:
        cutoff = now - WINDOW
        dq = self._staff_txns[sid]
        _prune(dq, cutoff)
        staff = self.world.staff.get(sid)
        lo, hi = staff.hours if staff else (9.5, 18.5)
        outflow = sum(a for _, a, _ in dq)
        max_amt = max((a for _, a, _ in dq), default=0.0)
        unknown = sum(1 for _, _, k in dq if not k)
        return [
            0.0, 0.0, 0.0,
            float(len(dq)),
            min(60.0, outflow / 500_000.0),
            min(60.0, max_amt / 500_000.0),
            unknown / len(dq) if dq else 0.0,
            self._hour_dev(now, lo, hi),
            0.0,
        ]
