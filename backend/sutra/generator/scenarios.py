"""Attack scenarios A/B/C and the borderline noise patterns.

Scenarios are deterministic event sequences relative to an injection time t0.
`instance` varies attacker infrastructure (device/ASN/payee) so a scenario can be
injected repeatedly in one live session and still trip novelty rules.

Borderline patterns are single-signal lookalikes: they fool naive siloed rules
(new device, raw velocity, off-hours) but carry the exculpatory half of the story
(familiar ASN, known payees, no EDR context) that fused scoring reads correctly.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from ..config import IST
from ..schemas import (AuthLogin, EdrAlert, Event, PayeeAdded, TlsSession, Txn)
from .noise import IdSource
from .world import CITIES, FOREIGN_GEOS, World


def _m(t0: datetime, minutes: float) -> datetime:
    return t0 + timedelta(minutes=minutes)


# ------------------------------------------------------------------ Scenario A
# Account takeover + structuring against CUST-0421.

def scenario_a(world: World, t0: datetime, rng: random.Random, ids: IdSource,
               instance: int = 0) -> list[Event]:
    victim = world.customers[world.victim_customer]
    acc = victim.accounts[0]
    asn = world.hostile_asns[instance % len(world.hostile_asns)]
    geo = list(FOREIGN_GEOS)[instance % len(FOREIGN_GEOS)]
    atk_ip = f"91.{200 + instance % 50}.{rng.randint(10, 250)}.{rng.randint(2, 250)}"
    atk_device = f"DEV-ATK{instance:02d}{rng.randrange(16**4):04X}"
    mule = f"PAYEE-MULE-{instance:02d}"

    others = [c for c in world.customers.values()
              if c.customer_id != victim.customer_id and not c.dormant]
    targets = rng.sample(others, 14) + [victim]
    events: list[Event] = []

    # t+0..t+3m: credential stuffing — 40 failures from one hostile ASN, 15 accounts.
    for i in range(40):
        tgt = targets[i % len(targets)]
        events.append(AuthLogin(
            event_id=ids.event(), ts=_m(t0, 3 * i / 40), scenario="A",
            customer_id=tgt.customer_id, account_id=tgt.accounts[0],
            device_id=f"DEV-BOT{rng.randrange(16**4):04X}", ip=atk_ip, asn=asn,
            geo=geo, success=False, channel="netbanking",
        ))

    # t+4m: successful takeover login — new device AND new ASN, foreign geo.
    events.append(AuthLogin(
        event_id=ids.event(), ts=_m(t0, 4), scenario="A",
        customer_id=victim.customer_id, account_id=acc, device_id=atk_device,
        ip=atk_ip, asn=asn, geo=geo, success=True, channel="netbanking",
    ))

    # t+6m: never-seen payee added from the same device.
    events.append(PayeeAdded(
        event_id=ids.event(), ts=_m(t0, 6), scenario="A",
        customer_id=victim.customer_id, account_id=acc, payee_id=mule,
        payee_name="QuickCash Traders", device_id=atk_device, ip=atk_ip,
    ))

    # t+9/12/15m: structuring — 3 UPI transfers just under the ₹50k threshold.
    for k in range(3):
        events.append(Txn(
            event_id=ids.event(), ts=_m(t0, 9 + 3 * k), scenario="A",
            txn_id=ids.txn(), account_id=acc, customer_id=victim.customer_id,
            txn_type="UPI", amount=49_900.0, payee_id=mule, payee_known=False,
            channel="netbanking", device_id=atk_device, ip=atk_ip, geo=geo,
        ))
    return events


# ------------------------------------------------------------------ Scenario B
# Compromised branch terminal TERM-114 / STAFF-77 draining a dormant business account.

def scenario_b(world: World, t0: datetime, rng: random.Random, ids: IdSource,
               instance: int = 0) -> list[Event]:
    staff = world.staff[world.compromised_staff]
    acc = world.scenario_b_account
    cust = world.customer_of_account(acc)
    events: list[Event] = [
        EdrAlert(
            event_id=ids.event(), ts=t0, scenario="B",
            terminal_id=staff.terminal_id, staff_id=staff.staff_id,
            malware_family="CobaltStrike-beacon", severity="med",
        ),
        Txn(
            event_id=ids.event(), ts=_m(t0, 7), scenario="B",
            txn_id=ids.txn(), account_id=acc, customer_id=cust.customer_id,
            txn_type="RTGS", amount=1_850_000.0,
            payee_id=f"PAYEE-SHELL-{instance:02d}", payee_known=False,
            channel="branch", terminal_id=staff.terminal_id, staff_id=staff.staff_id,
            ip=staff.branch_ip, geo="Pune",
        ),
    ]
    return events


# ------------------------------------------------------------------ Scenario C
# HNDL exfiltration: DB-2 bulk egress over quantum-vulnerable TLS to an unknown host.

def scenario_c(world: World, t0: datetime, rng: random.Random, ids: IdSource,
               instance: int = 0) -> list[Event]:
    dst = f"203.0.113.{60 + instance % 40}"
    events: list[Event] = []
    for i in range(6):
        events.append(TlsSession(
            event_id=ids.event(), ts=_m(t0, 2 * i), scenario="C",
            src=world.exfil_server, dst_ip=dst, dst_known=False,
            tls_version="1.2", key_exchange="RSA-2048",
            bytes_out=700_000_000,  # 6 × 700MB ≈ 4.2 GB
        ))
    return events


SCENARIOS = {"A": scenario_a, "B": scenario_b, "C": scenario_c}
SCENARIO_NAMES = {
    "A": "Account takeover + structuring",
    "B": "Compromised branch terminal",
    "C": "HNDL exfiltration (quantum)",
}


# ------------------------------------------------------------ borderline patterns

def _ist_time(day_start: datetime, hour: float) -> datetime:
    """day_start is 00:00 IST; return that day at `hour` IST."""
    return day_start + timedelta(hours=hour)


def borderline_events(world: World, day_start: datetime, rng: random.Random,
                      ids: IdSource) -> list[Event]:
    """~30 patterns over the batch day, 4 archetypes. Each fools a naive
    single-signal rule but is suppressed by fused scoring."""
    events: list[Event] = []
    retail = [c for c in world.customers.values()
              if c.segment == "retail" and not c.dormant
              and c.customer_id != world.victim_customer]
    business = [c for c in world.customers.values()
                if c.segment == "business" and not c.dormant
                and c.daily_outflow_mean >= 150_000]
    staff_pool = [s for s in world.staff.values()
                  if s.staff_id != world.compromised_staff]

    # 1) New phone, familiar network (x10): new device id, home ASN/geo, then a
    #    small txn to a known payee. Naive new-device rule FPs; fused R2 needs
    #    device AND asn to both be novel.
    for k, cust in enumerate(rng.sample(retail, 10)):
        t = _ist_time(day_start, 8.3 + k * 1.4)
        label = f"noise-newdevice-{k+1:02d}"
        new_dev = f"DEV-NP{rng.randrange(16**4):04X}"
        events.append(AuthLogin(
            event_id=ids.event(), ts=t, scenario=label,
            customer_id=cust.customer_id, account_id=cust.accounts[0],
            device_id=new_dev, ip=rng.choice(cust.ips), asn=cust.asns[0],
            geo=cust.home_geo, success=True, channel="mobile",
        ))
        events.append(Txn(
            event_id=ids.event(), ts=t + timedelta(minutes=2), scenario=label,
            txn_id=ids.txn(), account_id=cust.accounts[0],
            customer_id=cust.customer_id, txn_type="UPI",
            amount=round(rng.uniform(400, 3_000), 2),
            payee_id=rng.choice(cust.payees), payee_known=True, channel="mobile",
            device_id=new_dev, ip=rng.choice(cust.ips), geo=cust.home_geo,
        ))

    # 2) Business payment burst (x8): 3 large txns to KNOWN payees, ~2.4× the daily
    #    average inside an hour. Naive 2× velocity rule FPs; fused R5 needs 3×.
    for k, cust in enumerate(rng.sample(business, min(8, len(business)))):
        t = _ist_time(day_start, 10.1 + k * 1.1)
        label = f"noise-bizburst-{k+1:02d}"
        for j in range(3):
            events.append(Txn(
                event_id=ids.event(), ts=t + timedelta(minutes=20 * j), scenario=label,
                txn_id=ids.txn(), account_id=cust.accounts[0],
                customer_id=cust.customer_id, txn_type=rng.choice(["NEFT", "RTGS"]),
                amount=round(cust.daily_outflow_mean * 0.8, 2),
                payee_id=rng.choice(cust.payees), payee_known=True,
                channel="netbanking", device_id=rng.choice(cust.devices),
                ip=rng.choice(cust.ips), geo=cust.home_geo,
            ))

    # 3) Staff working late once (x6): a legitimate ₹1–1.6L branch txn at night with
    #    NO EDR context. Naive off-hours rule FPs; fused off-hours alone stays sub-60.
    for k, st in enumerate(rng.sample(staff_pool, 6)):
        t = _ist_time(day_start, 21.0 + k * 0.35)
        label = f"noise-latestaff-{k+1:02d}"
        cust = rng.choice(business)
        events.append(Txn(
            event_id=ids.event(), ts=t, scenario=label,
            txn_id=ids.txn(), account_id=cust.accounts[0],
            customer_id=cust.customer_id, txn_type="NEFT",
            amount=round(rng.uniform(100_000, 160_000), 2),
            payee_id=rng.choice(cust.payees), payee_known=True, channel="branch",
            terminal_id=st.terminal_id, staff_id=st.staff_id, ip=st.branch_ip,
            geo="Pune",
        ))

    # 4) Plausible travel (x6): same phone, new city + new ISP, then a normal txn.
    #    Naive new-ASN rule FPs; fused R2 stays quiet (device is known) and even a
    #    velocity hit alone can never reach the fused alert threshold.
    cities = list(CITIES)
    for k, cust in enumerate(rng.sample(retail[200:], 6)):
        t = _ist_time(day_start, 12.4 + k * 1.2)
        label = f"noise-travel-{k+1:02d}"
        away = rng.choice([c for c in cities if c != cust.home_geo])
        new_asn = rng.choice([a for a in world.benign_asns if a not in cust.asns])
        events.append(AuthLogin(
            event_id=ids.event(), ts=t, scenario=label,
            customer_id=cust.customer_id, account_id=cust.accounts[0],
            device_id=cust.devices[0], ip=f"49.{40+k}.{rng.randint(1,250)}.{rng.randint(2,250)}",
            asn=new_asn, geo=away, success=True, channel="mobile",
        ))
        events.append(Txn(
            event_id=ids.event(), ts=t + timedelta(minutes=3), scenario=label,
            txn_id=ids.txn(), account_id=cust.accounts[0],
            customer_id=cust.customer_id, txn_type="UPI",
            amount=round(rng.uniform(500, 4_000), 2),
            payee_id=rng.choice(cust.payees), payee_known=True, channel="mobile",
            device_id=cust.devices[0], ip=f"49.{40+k}.{rng.randint(1,250)}.{rng.randint(2,250)}",
            geo=away,
        ))

    return events
