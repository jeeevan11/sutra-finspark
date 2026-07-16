"""Benign background event streams.

Tuned so that at the fused threshold (risk >= 60) a benign-only day produces ZERO
alerts: known devices/ASNs/geos, known payees 90% of the time, amounts sampled from
each customer's baseline with the ₹44k–50k structuring band explicitly avoided and
unknown-payee amounts capped well under every rule threshold.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from ..config import IST
from ..schemas import (AuthLogin, Event, PasswordReset, PayeeAdded, TlsSession, Txn)
from .world import World

# events per simulated minute (Poisson means)
RATE_LOGIN_OK = 30.0
RATE_LOGIN_FAIL = 2.0
RATE_TXN = 45.0
RATE_TLS = 4.0
RATE_PAYEE_ADD = 0.2
RATE_PWD_RESET = 0.1


class IdSource:
    """Deterministic event/txn id allocation (per run)."""

    def __init__(self) -> None:
        self.n_evt = 0
        self.n_txn = 0

    def event(self) -> str:
        self.n_evt += 1
        return f"EVT-{self.n_evt:07d}"

    def txn(self) -> str:
        self.n_txn += 1
        return f"TXN-{self.n_txn:07d}"


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while p > limit:
        k += 1
        p *= rng.random()
    return k - 1


class NoiseGenerator:
    def __init__(self, world: World, rng: random.Random, ids: IdSource) -> None:
        self.world = world
        self.rng = rng
        self.ids = ids
        self.active_by_hour: dict[int, list[str]] = {}
        non_dormant = [c.customer_id for c in world.customers.values() if not c.dormant]
        for h in range(24):
            bucket = [
                c.customer_id for c in world.customers.values()
                if not c.dormant and c.active_hours[0] <= h < c.active_hours[1]
            ]
            self.active_by_hour[h] = bucket or non_dormant
        self._non_dormant = non_dormant

    # ------------------------------------------------------------------ helpers

    def _pick_customer(self, ts: datetime) -> str:
        hour = ts.astimezone(IST).hour
        return self.rng.choice(self.active_by_hour[hour])

    def _rate_mult(self, ts: datetime) -> float:
        hour = ts.astimezone(IST).hour
        return 1.0 if 7 <= hour < 23 else 0.6

    def _sec(self, minute_start: datetime) -> datetime:
        return minute_start + timedelta(seconds=self.rng.uniform(0, 59.9))

    def _txn_amount(self, daily_mean: float) -> float:
        # A single txn is a lognormal slice of the daily baseline; resample away from
        # the structuring band so R4 can never fire on benign traffic (synthetic-data
        # tuning, stated in the benchmark methodology note).
        for _ in range(6):
            amt = round(math.exp(self.rng.gauss(math.log(max(daily_mean, 200) / 8), 0.55)), 2)
            if not (44_000 <= amt < 50_000):
                return max(10.0, amt)
        return 39_500.0

    def _login(self, ts: datetime, success: bool) -> AuthLogin:
        w, rng = self.world, self.rng
        cust = w.customers[self._pick_customer(ts)]
        return AuthLogin(
            event_id=self.ids.event(), ts=ts,
            customer_id=cust.customer_id, account_id=rng.choice(cust.accounts),
            device_id=rng.choice(cust.devices), ip=rng.choice(cust.ips),
            asn=rng.choice(cust.asns), geo=cust.home_geo, success=success,
            channel=rng.choice(["netbanking", "mobile", "mobile"]),
        )

    def _txn(self, ts: datetime) -> Txn:
        w, rng = self.world, self.rng
        cust = w.customers[self._pick_customer(ts)]
        known = rng.random() < 0.9
        if known:
            payee = rng.choice(cust.payees)
            amount = self._txn_amount(cust.daily_outflow_mean)
        else:
            payee = rng.choice(w.payee_pool)
            amount = min(self._txn_amount(cust.daily_outflow_mean), 90_000.0)
        return Txn(
            event_id=self.ids.event(), ts=ts, txn_id=self.ids.txn(),
            account_id=rng.choice(cust.accounts), customer_id=cust.customer_id,
            txn_type=rng.choice(["UPI", "UPI", "UPI", "IMPS", "NEFT"]),
            amount=amount, payee_id=payee, payee_known=known,
            channel=rng.choice(["mobile", "mobile", "netbanking"]),
            device_id=rng.choice(cust.devices), ip=rng.choice(cust.ips),
            geo=cust.home_geo,
        )

    def _tls(self, ts: datetime) -> TlsSession:
        w, rng = self.world, self.rng
        if rng.random() < 0.85:
            server = w.servers[rng.choice(list(w.servers))]
            src = server.server_id
            kexes, weights = zip(*server.kex_weights.items())
            kex = rng.choices(kexes, weights=weights)[0]
        else:
            src = rng.choice(list(w.terminals))
            kex = "X25519Kyber768-hybrid" if rng.random() < 0.7 else "X25519"
        known = rng.random() < 0.95
        if known:
            dst, cap = rng.choice(w.known_tls_dsts), 80e6
        else:
            dst, cap = f"185.{rng.randint(10, 250)}.{rng.randint(1, 250)}.{rng.randint(2, 250)}", 30e6
        bytes_out = int(min(cap, math.exp(rng.gauss(math.log(8e6), 1.0))))
        return TlsSession(
            event_id=self.ids.event(), ts=ts, src=src, dst_ip=dst, dst_known=known,
            tls_version="1.2" if kex in ("RSA-2048",) else "1.3",
            key_exchange=kex, bytes_out=bytes_out,
        )

    def _payee_added(self, ts: datetime) -> PayeeAdded:
        w, rng = self.world, self.rng
        cust = w.customers[self._pick_customer(ts)]
        payee = rng.choice(w.payee_pool)
        return PayeeAdded(
            event_id=self.ids.event(), ts=ts, customer_id=cust.customer_id,
            account_id=rng.choice(cust.accounts), payee_id=payee,
            payee_name=f"Beneficiary {payee[-4:]}", device_id=rng.choice(cust.devices),
            ip=rng.choice(cust.ips),
        )

    def _pwd_reset(self, ts: datetime) -> PasswordReset:
        w, rng = self.world, self.rng
        cust = w.customers[self._pick_customer(ts)]
        return PasswordReset(
            event_id=self.ids.event(), ts=ts, customer_id=cust.customer_id,
            device_id=rng.choice(cust.devices), ip=rng.choice(cust.ips),
            asn=rng.choice(cust.asns),
        )

    # ------------------------------------------------------------------ public

    def minute(self, minute_start: datetime) -> list[Event]:
        """All benign events for one simulated minute (unsorted)."""
        rng, mult = self.rng, self._rate_mult(minute_start)
        out: list[Event] = []
        for _ in range(_poisson(rng, RATE_LOGIN_OK * mult)):
            out.append(self._login(self._sec(minute_start), True))
        for _ in range(_poisson(rng, RATE_LOGIN_FAIL * mult)):
            out.append(self._login(self._sec(minute_start), False))
        for _ in range(_poisson(rng, RATE_TXN * mult)):
            out.append(self._txn(self._sec(minute_start)))
        for _ in range(_poisson(rng, RATE_TLS * mult)):
            out.append(self._tls(self._sec(minute_start)))
        for _ in range(_poisson(rng, RATE_PAYEE_ADD * mult)):
            out.append(self._payee_added(self._sec(minute_start)))
        for _ in range(_poisson(rng, RATE_PWD_RESET * mult)):
            out.append(self._pwd_reset(self._sec(minute_start)))
        return out
