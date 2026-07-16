"""End-to-end scenario detection through the fused pipeline (PS2 outcomes 1–3, 5)."""

import pytest

from sutra.fusion import FusionEngine
from sutra.generator.replay import batch_events
from sutra.graph import EntityGraph
from sutra.rules.engine import RuleEngine


def _run_fused(world, ml, **kwargs):
    fusion = FusionEngine(world, RuleEngine(world, "fused"), EntityGraph(), ml=ml)
    for ev in batch_events(world, 42, **kwargs):
        fusion.ingest(ev)
    return fusion


def test_scenario_a_quiet_world(world, ml):
    fusion = _run_fused(world, ml, include_noise=False, include_borderline=False,
                        scenarios=("A",))
    assert len(fusion.alerts) == 1, "exactly one fused alert for the whole campaign"
    a = next(iter(fusion.alerts.values()))
    assert a.risk >= 90
    assert a.severity == "critical"
    rules = {h.rule_id for h in a.rule_hits}
    assert {"R1", "R2", "R3", "R4"} <= rules
    assert len(a.evidence) >= 6
    assert a.entity_id == world.victim_customer
    assert a.scenario_guess == "ato"
    assert a.status == "open"  # actions available
    assert "49,900" in a.narrative and "structuring" in a.narrative.lower()


def test_scenario_b_quiet_world(world, ml):
    fusion = _run_fused(world, ml, include_noise=False, include_borderline=False,
                        scenarios=("B",))
    assert len(fusion.alerts) == 1
    a = next(iter(fusion.alerts.values()))
    assert a.risk >= 85
    rules = {h.rule_id for h in a.rule_hits}
    assert {"R6", "R7"} <= rules
    assert a.entity_id == world.compromised_terminal
    assert a.scenario_guess == "terminal_compromise"
    # the correlation claim: each half is weak, fused is strong
    assert a.risk >= 85 > max(h.points for h in a.rule_hits)


def test_scenario_c_quiet_world(world, ml):
    fusion = _run_fused(world, ml, include_noise=False, include_borderline=False,
                        scenarios=("C",))
    assert len(fusion.alerts) == 1
    a = next(iter(fusion.alerts.values()))
    assert a.risk >= 80
    assert {h.rule_id for h in a.rule_hits} == {"R8"}
    assert "quantum" in a.tags
    assert a.entity_id == world.exfil_server
    assert a.scenario_guess == "quantum_exfil"


@pytest.mark.slow
def test_benign_day_zero_alerts(world, ml):
    """PS2 outcome 5 (false-positive reduction): a full benign day, including the
    30 borderline single-signal lookalikes, produces ZERO fused alerts."""
    fusion = _run_fused(world, ml, include_borderline=True, scenarios=())
    assert fusion.alerts == {}


def test_full_day_exactly_three_alerts(world, ml):
    fusion = _run_fused(world, ml)  # noise + borderline + A/B/C
    assert len(fusion.alerts) == 3
    guesses = sorted(a.scenario_guess for a in fusion.alerts.values())
    assert guesses == ["ato", "quantum_exfil", "terminal_compromise"]
    assert all(a.risk >= 80 for a in fusion.alerts.values())
