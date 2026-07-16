"""Unit tests: every rule's trigger and non-trigger case."""

from datetime import datetime, timedelta, timezone

import pytest

from sutra.rules.engine import RuleEngine
from sutra.schemas import AuthLogin, EdrAlert, PayeeAdded, TlsSession, Txn

T0 = datetime(2026, 2, 14, 6, 0, 0, tzinfo=timezone.utc)  # 11:30 IST
NIGHT = datetime(2026, 2, 14, 17, 0, 0, tzinfo=timezone.utc)  # 22:30 IST

_n = [0]


def _eid() -> str:
    _n[0] += 1
    return f"TEV-{_n[0]:05d}"


def login(world, cust_id, *, ts, success=True, device=None, asn=None, geo=None,
          account=None):
    c = world.customers[cust_id]
    return AuthLogin(event_id=_eid(), ts=ts, customer_id=cust_id,
                     account_id=account or c.accounts[0],
                     device_id=device or c.devices[0], ip="49.10.1.2",
                     asn=asn or c.asns[0], geo=geo or c.home_geo, success=success,
                     channel="mobile")


def txn(world, cust_id, amount, *, ts, payee_known=True, staff=None, terminal=None):
    c = world.customers[cust_id]
    return Txn(event_id=_eid(), ts=ts, txn_id=_eid(), account_id=c.accounts[0],
               customer_id=cust_id, txn_type="UPI", amount=amount,
               payee_id="PAYEE-0001", payee_known=payee_known,
               channel="branch" if staff else "mobile",
               device_id=None if staff else c.devices[0],
               terminal_id=terminal, staff_id=staff, ip="49.10.1.2", geo=c.home_geo)


def tls(src, bytes_out, *, ts, kex="RSA-2048", known=False):
    return TlsSession(event_id=_eid(), ts=ts, src=src, dst_ip="203.0.113.9",
                      dst_known=known, tls_version="1.2", key_exchange=kex,
                      bytes_out=bytes_out)


@pytest.fixture()
def engine(world):
    return RuleEngine(world, "fused")


def _rules(hits):
    return [h.rule_id for h in hits]


def test_r1_burst(world, engine):
    hits = []
    for i in range(25):
        ev = login(world, f"CUST-{(i % 15) + 1:04d}", ts=T0 + timedelta(seconds=6 * i),
                   success=False, asn="AS64000", device="DEV-XBOT")
        hits += engine.observe(ev)
    r1 = [h for h in hits if h.rule_id == "R1"]
    assert len(r1) == 1, "fires once per burst, no refire spam"
    assert r1[0].entities[0] == "AS64000"
    assert "CUST-0001" in r1[0].entities  # taints touched customers


def test_r1_below_threshold(world, engine):
    hits = []
    for i in range(20):
        hits += engine.observe(login(world, "CUST-0002", ts=T0 + timedelta(seconds=6 * i),
                                     success=False, asn="AS64001"))
    assert "R1" not in _rules(hits)


def test_r2_requires_both_novel(world, engine):
    both = engine.observe(login(world, "CUST-0003", ts=T0, device="DEV-NEW1", asn="AS64002"))
    assert "R2" in _rules(both)
    dev_only = engine.observe(login(world, "CUST-0004", ts=T0, device="DEV-NEW2"))
    assert "R2" not in _rules(dev_only)
    asn_only = engine.observe(login(world, "CUST-0005", ts=T0, asn="AS64003"))
    assert "R2" not in _rules(asn_only)


def test_r3_payee_after_suspicious_login(world, engine):
    c = world.customers["CUST-0006"]
    engine.observe(login(world, "CUST-0006", ts=T0, device="DEV-NEW3", asn="AS64004"))
    ev = PayeeAdded(event_id=_eid(), ts=T0 + timedelta(minutes=10),
                    customer_id="CUST-0006", account_id=c.accounts[0],
                    payee_id="PAYEE-MULE-XX", payee_name="X", device_id="DEV-NEW3",
                    ip="1.2.3.4")
    assert "R3" in _rules(engine.observe(ev))
    # without a prior R2: no hit
    ev2 = PayeeAdded(event_id=_eid(), ts=T0, customer_id="CUST-0007",
                     account_id=world.customers["CUST-0007"].accounts[0],
                     payee_id="PAYEE-0009", payee_name="X", device_id="D", ip="1.2.3.4")
    assert "R3" not in _rules(engine.observe(ev2))


def test_r4_structuring(world, engine):
    hits = []
    for i, amt in enumerate([49_900, 45_500, 49_000]):
        hits += engine.observe(txn(world, "CUST-0008", amt, ts=T0 + timedelta(minutes=5 * i)))
    assert "R4" in _rules(hits)
    # two in-band txns only: no hit
    hits2 = []
    for i, amt in enumerate([49_900, 45_500]):
        hits2 += engine.observe(txn(world, "CUST-0009", amt, ts=T0 + timedelta(minutes=5 * i)))
    assert "R4" not in _rules(hits2)
    # below the band does not count
    hits3 = []
    for i, amt in enumerate([44_000, 44_500, 43_900]):
        hits3 += engine.observe(txn(world, "CUST-0010", amt, ts=T0 + timedelta(minutes=5 * i)))
    assert "R4" not in _rules(hits3)


def test_r5_velocity(world, engine):
    c = world.customers["CUST-0011"]
    big = c.daily_outflow_mean * 2
    hits = []
    for i in range(2):
        hits += engine.observe(txn(world, "CUST-0011", big, ts=T0 + timedelta(minutes=i)))
    assert "R5" in _rules(hits)
    hits2 = engine.observe(txn(world, "CUST-0012",
                               world.customers["CUST-0012"].daily_outflow_mean * 0.5, ts=T0))
    assert "R5" not in _rules(hits2)


def test_r6_edr_then_txn(world, engine):
    st = world.staff[world.compromised_staff]
    edr = EdrAlert(event_id=_eid(), ts=T0, terminal_id=st.terminal_id,
                   staff_id=st.staff_id, malware_family="Emotet", severity="med")
    engine.observe(edr)
    cust = world.customer_of_account(world.scenario_b_account).customer_id
    hits = engine.observe(txn(world, cust, 600_000, ts=T0 + timedelta(minutes=30),
                              staff=st.staff_id, terminal=st.terminal_id))
    assert "R6" in _rules(hits)
    # below amount threshold: no R6
    hits2 = engine.observe(txn(world, cust, 400_000, ts=T0 + timedelta(minutes=31),
                               staff=st.staff_id, terminal=st.terminal_id))
    assert "R6" not in _rules(hits2)
    # stale EDR (>60m): no R6
    engine2 = RuleEngine(world, "fused")
    engine2.observe(edr)
    hits3 = engine2.observe(txn(world, cust, 600_000, ts=T0 + timedelta(minutes=75),
                                staff=st.staff_id, terminal=st.terminal_id))
    assert "R6" not in _rules(hits3)


def test_r7_off_hours(world, engine):
    st = next(iter(world.staff.values()))
    cust = "CUST-0013"
    night = engine.observe(txn(world, cust, 150_000, ts=NIGHT, staff=st.staff_id,
                               terminal=st.terminal_id))
    assert "R7" in _rules(night)
    day = engine.observe(txn(world, cust, 150_000, ts=T0, staff=st.staff_id,
                             terminal=st.terminal_id))
    assert "R7" not in _rules(day)
    small = engine.observe(txn(world, cust, 90_000, ts=NIGHT, staff=st.staff_id,
                               terminal=st.terminal_id))
    assert "R7" not in _rules(small)


def test_r8_escalating_egress(world, engine):
    hits = []
    for i in range(6):
        hits += engine.observe(tls("DB-2", 700_000_000, ts=T0 + timedelta(minutes=2 * i)))
    r8 = [h for h in hits if h.rule_id == "R8"]
    assert len(r8) == 4, "4.2 GB crosses four whole-GB escalation levels"
    assert len({h.dedup_key for h in r8}) == 4
    # known destination: never fires
    e2 = RuleEngine(world, "fused")
    assert not e2.observe(tls("DB-1", 2_000_000_000, ts=T0, known=True))
    # PQC-safe key exchange: never fires
    assert not e2.observe(tls("APP-1", 2_000_000_000, ts=T0, kex="X25519Kyber768-hybrid"))


def test_r9_dormant(world, engine):
    acc = world.scenario_b_account
    cust = world.customer_of_account(acc).customer_id
    first = engine.observe(txn(world, cust, 5_000, ts=T0))
    assert "R9" in _rules(first)
    second = engine.observe(txn(world, cust, 5_000, ts=T0 + timedelta(minutes=1)))
    assert "R9" not in _rules(second)


def test_r10_impossible_travel(world, engine):
    engine.observe(login(world, "CUST-0014", ts=T0, geo="Mumbai"))
    fast = engine.observe(login(world, "CUST-0014", ts=T0 + timedelta(minutes=5), geo="Delhi"))
    assert "R10" in _rules(fast)
    engine.observe(login(world, "CUST-0015", ts=T0, geo="Mumbai"))
    slow = engine.observe(login(world, "CUST-0015", ts=T0 + timedelta(hours=2), geo="Delhi"))
    assert "R10" not in _rules(slow)


def test_r10_dedup_round_trip(world, engine):
    engine.observe(login(world, "CUST-0016", ts=T0, geo="Mumbai"))
    out = engine.observe(login(world, "CUST-0016", ts=T0 + timedelta(minutes=5), geo="Delhi"))
    back = engine.observe(login(world, "CUST-0016", ts=T0 + timedelta(minutes=10), geo="Mumbai"))
    assert "R10" in _rules(out) and "R10" not in _rules(back)


def test_r11_unknown_high_value(world, engine):
    big = engine.observe(txn(world, "CUST-0017", 1_200_000, ts=T0, payee_known=False))
    assert "R11" in _rules(big)
    known = engine.observe(txn(world, "CUST-0018", 1_200_000, ts=T0, payee_known=True))
    assert "R11" not in _rules(known)
    small = engine.observe(txn(world, "CUST-0019", 900_000, ts=T0, payee_known=False))
    assert "R11" not in _rules(small)


def test_siloed_naive_variants(world):
    eng = RuleEngine(world, "siloed")
    # new device alone DOES fire in siloed mode (the FP the demo hinges on)
    hits = eng.observe(login(world, "CUST-0020", ts=T0, device="DEV-NEWPHONE"))
    assert "S2" in _rules(hits)
    # fused rules don't exist in siloed mode
    assert eng._c("R3") is None and eng._c("R6") is None and eng._c("R8") is None
    # quantum egress is invisible to the siloed stack
    assert not eng.observe(tls("DB-2", 2_000_000_000, ts=T0))
