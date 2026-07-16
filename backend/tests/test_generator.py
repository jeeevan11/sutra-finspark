"""Generator invariants: determinism, scenario shapes, benign-noise tuning."""

from datetime import timedelta

from sutra.config import BATCH_SIM_START, IST
from sutra.generator.noise import IdSource
from sutra.generator.replay import batch_events
from sutra.generator.scenarios import scenario_a, scenario_b, scenario_c
from sutra.generator.world import build_world

import random


def test_world_is_deterministic():
    w1, w2 = build_world(42), build_world(42)
    assert list(w1.customers) == list(w2.customers)
    c1 = w1.customers["CUST-0123"]
    c2 = w2.customers["CUST-0123"]
    assert (c1.devices, c1.asns, c1.daily_outflow_mean) == (c2.devices, c2.asns, c2.daily_outflow_mean)
    assert w1.scenario_b_account == w2.scenario_b_account


def test_world_anchors(world):
    assert world.victim_customer in world.customers
    assert not world.customers[world.victim_customer].dormant
    assert world.compromised_terminal in world.terminals
    assert world.terminals[world.compromised_terminal] == world.compromised_staff
    assert world.scenario_b_account in world.dormant_accounts
    assert world.customer_of_account(world.scenario_b_account).segment == "business"
    assert world.exfil_server in world.servers


def test_batch_deterministic(world):
    e1 = batch_events(world, 42, hours=1.0)
    e2 = batch_events(build_world(42), 42, hours=1.0)
    assert len(e1) == len(e2)
    assert [x.event_id for x in e1[:500]] == [x.event_id for x in e2[:500]]
    assert [x.ts for x in e1[:500]] == [x.ts for x in e2[:500]]


def test_scenario_a_shape(world):
    evs = scenario_a(world, BATCH_SIM_START, random.Random(1), IdSource())
    fails = [e for e in evs if e.type == "auth_login" and not e.success]
    okays = [e for e in evs if e.type == "auth_login" and e.success]
    txns = [e for e in evs if e.type == "txn"]
    assert len(fails) == 40
    assert len({e.asn for e in fails}) == 1
    assert len({e.account_id for e in fails}) == 15
    assert len(okays) == 1 and okays[0].customer_id == world.victim_customer
    assert len([e for e in evs if e.type == "payee_added"]) == 1
    assert len(txns) == 3 and all(t.amount == 49_900.0 for t in txns)
    assert all(e.scenario == "A" for e in evs)
    assert evs[-1].ts - evs[0].ts == timedelta(minutes=15)


def test_scenario_b_shape(world):
    evs = scenario_b(world, BATCH_SIM_START + timedelta(hours=22.55), random.Random(1), IdSource())
    assert [e.type for e in evs] == ["edr_alert", "txn"]
    edr, txn = evs
    assert edr.terminal_id == txn.terminal_id == world.compromised_terminal
    assert txn.amount == 1_850_000.0 and txn.channel == "branch" and not txn.payee_known
    assert txn.account_id == world.scenario_b_account
    # off-hours: 22:40 IST
    ist_h = txn.ts.astimezone(IST).hour + txn.ts.astimezone(IST).minute / 60
    assert ist_h > 18.5 or ist_h < 9.5


def test_scenario_c_shape(world):
    evs = scenario_c(world, BATCH_SIM_START, random.Random(1), IdSource())
    assert len(evs) == 6
    assert all(e.src == world.exfil_server for e in evs)
    assert all(e.key_exchange == "RSA-2048" and not e.dst_known for e in evs)
    assert sum(e.bytes_out for e in evs) >= 4_000_000_000


def test_benign_noise_tuning(world):
    evs = batch_events(world, 42, hours=3.0, include_borderline=False, scenarios=())
    txns = [e for e in evs if e.type == "txn"]
    assert txns, "noise should contain transactions"
    # structuring band is never sampled
    assert not [t for t in txns if 44_000 <= t.amount < 50_000]
    # unknown payees stay far below the R11 threshold
    assert all(t.amount < 1_000_000 for t in txns if not t.payee_known)
    # only known devices/ASNs are used
    for e in evs[:3000]:
        if e.type == "auth_login":
            cust = world.customers[e.customer_id]
            assert e.device_id in cust.devices and e.asn in cust.asns
    # dormant customers stay quiet
    dormant = {c.customer_id for c in world.customers.values() if c.dormant}
    assert not [t for t in txns if t.customer_id in dormant]


def test_borderline_patterns(world):
    evs = batch_events(world, 42, hours=24.0, scenarios=())
    labels = {e.scenario for e in evs if e.scenario.startswith("noise-")}
    archetypes = {l.rsplit("-", 1)[0] for l in labels}
    assert len(labels) == 30
    assert archetypes == {"noise-newdevice", "noise-bizburst", "noise-latestaff", "noise-travel"}
