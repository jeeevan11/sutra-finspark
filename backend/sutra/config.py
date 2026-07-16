"""Central configuration. Everything deterministic flows from SEED."""

import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SEED = int(os.environ.get("SUTRA_SEED", "42"))
BUS_MODE = os.environ.get("SUTRA_BUS", "memory")  # "redis" | "memory"
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATA_DIR = Path(os.environ.get("SUTRA_DATA_DIR", "data"))
# repo-root/deliverables when running from a checkout; overridden in Docker
DELIVERABLES_DIR = Path(os.environ.get(
    "SUTRA_DELIVERABLES_DIR", str(Path(__file__).resolve().parents[2] / "deliverables")))

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

# The simulated clock is decoupled from wall time so the demo always plays out at a
# story-friendly hour (20:30 IST — after branch hours, so Scenario B's staff txn is
# off-hours no matter when the live demo runs) and stays identical between rehearsal
# and stage.
LIVE_SIM_START = datetime(2026, 2, 14, 15, 0, 0, tzinfo=UTC)  # 20:30 IST
# Batch/benchmark day: 24h starting at 00:00 IST on 14 Feb 2026.
BATCH_SIM_START = datetime(2026, 2, 13, 18, 30, 0, tzinfo=UTC)

# Risk fusion (see CLAUDE.md): risk = min(100, 0.65*points + 0.35*(ml*2.5))
RULE_WEIGHT = 0.65
ML_WEIGHT = 0.35
ALERT_THRESHOLD = 60
SILOED_THRESHOLD = 25  # points, single-domain, no ML
INCIDENT_WINDOW_MIN = 45
ML_MIN_POINTS = 25  # ML is only consulted once rules have this many points

SEVERITY_BANDS = ((90, "critical"), (75, "high"), (60, "medium"))


def severity_for(risk: int) -> str:
    for floor, name in SEVERITY_BANDS:
        if risk >= floor:
            return name
    return "medium"


def ist(ts: datetime) -> datetime:
    return ts.astimezone(IST)
