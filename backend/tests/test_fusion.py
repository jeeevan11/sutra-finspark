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


def test_action_evidence_does_not_skew_update_dedup(world):
    """After an operator action appends an action-type EvidenceItem, a later
    detection hit that adds a genuinely new event must still update the alert —
    the dedup guard must compare non-action evidence only (finding #7)."""
    import asyncio

    from sutra.actions import ActionAdapter
    from sutra.schemas import EvidenceItem
    from datetime import timezone

    fusion = FusionEngine(world, RuleEngine(world, "fused"), EntityGraph())
    fusion.graph.ingest(_txn_event(world, "CUST-0201", "E1"))
    h1 = _hit(95, ["CUST-0201"], T0, "k1", ["E1"])
    inc = fusion._route(h1); fusion._apply(inc, h1)
    note = fusion._score_and_alert(inc, T0)
    assert note is not None
    alert = fusion.alerts[inc.alert_id]

    # simulate an applied action: append an action-type evidence item
    alert.evidence.append(EvidenceItem(
        event_id="ACT-0001", ts=T0, type="action", summary="[HOLD] held",
        entity_refs=[], rule_ids=[], detail={"action": "hold"}))
    n_before = len([e for e in alert.evidence if e.type != "action"])

    # a new detection event on the same incident (risk unchanged, still capped)
    fusion.graph.ingest(_txn_event(world, "CUST-0201", "E2"))
    h2 = _hit(95, ["CUST-0201"], T0, "k2", ["E2"])
    fusion._apply(inc, h2)
    out = fusion._score_and_alert(inc, T0)

    assert out is not None, "new evidence must produce an update, not be dropped"
    n_after = len([e for e in alert.evidence if e.type != "action"])
    assert n_after > n_before, "the new event must appear in evidence"
    # the action item survives the update
    assert any(e.type == "action" for e in alert.evidence)


def test_bus_drops_malformed_entry_without_dying():
    """A malformed wire dict must be dropped, not propagate out of consume() and
    kill the consumer (finding #5)."""
    import asyncio

    from sutra.bus import MemoryBus
    from sutra.generator.world import build_world
    from sutra.generator.noise import IdSource
    from sutra.generator.scenarios import scenario_c
    from sutra.config import BATCH_SIM_START

    async def run():
        bus = MemoryBus()
        good = scenario_c(build_world(42), BATCH_SIM_START, __import__("random").Random(1), IdSource())[0]
        await bus.publish(good)
        await bus.q.put({"type": "not_a_real_event", "event_id": "X", "ts": "2026-01-01T00:00:00+00:00"})
        await bus.publish(good)
        gen = bus.consume()
        first = await asyncio.wait_for(gen.__anext__(), timeout=2)
        second = await asyncio.wait_for(gen.__anext__(), timeout=2)  # skips the bad one
        return first.event_id, second.event_id

    a, b = asyncio.run(run())
    assert a == b, "both yielded events are the good one; the malformed entry was skipped"


def test_replay_loop_survives_emit_error(world):
    """A transient emit failure must not kill the replay loop or leave status()
    falsely reporting running (finding #3), and _emit_wall_ts stays bounded
    (finding #4)."""
    import asyncio
    from sutra.generator.replay import LiveReplay

    async def run():
        calls = {"n": 0}
        async def flaky(_ev):
            calls["n"] += 1
            if calls["n"] % 3 == 0:
                raise ConnectionError("redis blip")  # transient
        replay = LiveReplay(world, 42, emit=flaky)
        replay.start(20)
        await asyncio.sleep(1.2)  # let the loop emit + hit some errors
        running = replay.running
        task_alive = replay._task is not None and not replay._task.done()
        emitted = replay.events_emitted
        await replay.stop()
        return running, task_alive, emitted, calls["n"]

    running, task_alive, emitted, attempted = asyncio.run(run())
    assert running and task_alive, "loop survived transient emit errors"
    assert attempted > emitted, "some emits raised but were dropped, not fatal"
    assert emitted > 0, "good emits still counted"


def test_action_during_reset_is_aborted(world):
    """An action in flight when its engine is retired (demo reset) must abort
    rather than write into the wiped store / reset chain (finding #6)."""
    import asyncio
    from sutra.actions import ActionAdapter
    from sutra.pqc import AlertSigner
    from sutra.store import AlertStore

    signer, store = AlertSigner(), AlertStore()
    fusion = FusionEngine(world, RuleEngine(world, "fused"), EntityGraph(),
                          signer=signer, store=store)
    fusion.graph.ingest(_txn_event(world, "CUST-0202", "F1"))
    h = _hit(95, ["CUST-0202"], T0, "k", ["F1"])
    inc = fusion._route(h); fusion._apply(inc, h)
    fusion._score_and_alert(inc, T0)
    aid = inc.alert_id
    adapter = ActionAdapter(fusion)

    async def run():
        task = asyncio.create_task(adapter.apply(aid, "hold"))
        await asyncio.sleep(0.05)     # action is mid-latency
        fusion.active = False         # reset retires the engine
        try:
            await task
            return "completed"
        except KeyError:
            return "aborted"

    outcome = asyncio.run(run())
    assert outcome == "aborted", "stale action must not write after reset"
