"""Fusion incident-correlation edge cases."""

from datetime import datetime, timedelta, timezone

from sutra.fusion import FusionEngine
from sutra.graph import EntityGraph
from sutra.rules.engine import Hit, RuleEngine
from sutra.schemas import Txn

T0 = datetime(2026, 2, 14, 6, 0, 0, tzinfo=timezone.utc)


def _txn_event(world, cust_id, eid):
    c = world.customers[cust_id]
    return Txn(event_id=eid, ts=T0, txn_id=f"TX-{eid}", account_id=c.accounts[0],
               customer_id=cust_id, txn_type="UPI", amount=1000.0,
               payee_id="PAYEE-0001", payee_known=True, channel="mobile",
               device_id=c.devices[0], ip="49.1.1.1", geo=c.home_geo)


def _hit(points, entities, ts, key, event_ids):
    return Hit("RX", "synthetic", "security", points, "synthetic hit", ts,
               entities, event_ids, key)


def test_merge_consolidates_already_alerted_incidents(world):
    """When two incidents that EACH already raised an alert later share an
    entity, the absorbed alert must be retired visibly (dismissed, pointing at
    the survivor) — never left orphaned open at a stale risk."""
    fusion = FusionEngine(world, RuleEngine(world, "fused"), EntityGraph())
    for cid, eid in (("CUST-0101", "SYN-1"), ("CUST-0102", "SYN-2")):
        fusion.graph.ingest(_txn_event(world, cid, eid))

    # two disjoint incidents, each independently over the alert threshold
    h1 = _hit(95, ["CUST-0101"], T0, "k1", ["SYN-1"])
    inc1 = fusion._route(h1)
    fusion._apply(inc1, h1)
    fusion._score_and_alert(inc1, T0)
    h2 = _hit(95, ["CUST-0102"], T0 + timedelta(minutes=1), "k2", ["SYN-2"])
    inc2 = fusion._route(h2)
    fusion._apply(inc2, h2)
    fusion._score_and_alert(inc2, T0 + timedelta(minutes=1))
    assert len(fusion.alerts) == 2
    assert all(a.status == "open" for a in fusion.alerts.values())

    # a bridging hit touches both incidents -> they merge
    bridge = _hit(30, ["CUST-0101", "CUST-0102"], T0 + timedelta(minutes=2),
                  "k3", ["SYN-1", "SYN-2"])
    inc = fusion._route(bridge)
    fusion._apply(inc, bridge)
    fusion._score_and_alert(inc, T0 + timedelta(minutes=2))

    assert len(fusion.incidents) == 1
    open_alerts = [a for a in fusion.alerts.values() if a.status == "open"]
    dismissed = [a for a in fusion.alerts.values() if a.status == "dismissed"]
    assert len(open_alerts) == 1 and len(dismissed) == 1
    assert open_alerts[0].alert_id == inc.alert_id
    assert dismissed[0].narrative.startswith(f"[Merged into {inc.alert_id}")
    # the survivor keeps the union of evidence
    assert {e.event_id for e in open_alerts[0].evidence} >= {"SYN-1", "SYN-2"}


def test_inject_never_clears_operator_pause(world):
    """Demo-control invariant: injecting a scenario while paused stages events
    but must not resume the sim clock."""
    import asyncio

    from sutra.generator.replay import LiveReplay

    async def scenario() -> tuple[bool, bool]:
        async def emit(_ev):
            return None
        replay = LiveReplay(world, 42, emit=emit)
        replay.start(20)
        replay.pause_toggle()
        assert replay.paused
        replay.ensure_running()   # what the inject endpoint calls
        replay.inject("A")
        paused_after = replay.paused
        await replay.stop()
        return paused_after, len(replay._pending) > 0

    paused_after, staged = asyncio.run(scenario())
    assert paused_after, "inject must not resume a paused demo"
    assert staged, "scenario events are staged for when the operator resumes"
