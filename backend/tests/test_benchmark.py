"""Benchmark thresholds: the headline siloed-vs-fused claims must hold."""

import pytest

from bench.benchmark import run_benchmark


@pytest.fixture(scope="module")
def metrics(world, ml):
    return run_benchmark(seed=42, write=False, ml=ml)


def test_alert_volume_reduction(metrics):
    fused = metrics["modes"]["fused"]["total_alerts"]
    siloed = metrics["modes"]["siloed"]["total_alerts"]
    assert fused <= 0.25 * siloed, f"fused {fused} must be ≤ 25% of siloed {siloed}"


def test_fused_full_recall(metrics):
    assert metrics["modes"]["fused"]["recall"] == 1.0
    assert metrics["modes"]["fused"]["detected_scenarios"] == ["A", "B", "C"]
    for s in ("A", "B", "C"):
        assert metrics["scenarios"][s]["fused"]["detected"]


def test_fused_fewer_false_positives(metrics):
    assert (metrics["modes"]["fused"]["false_positives"]
            < metrics["modes"]["siloed"]["false_positives"])


def test_siloed_misses_quantum(metrics):
    assert not metrics["scenarios"]["C"]["siloed"]["detected"]


def test_summary_fields_present(metrics):
    s = metrics["summary"]
    assert s["alert_reduction_pct"] > 0
    assert s["analyst_hours_saved_per_day"] > 0
    assert s["rupees_at_risk_flagged"] >= 1_999_700  # A structuring + B RTGS
