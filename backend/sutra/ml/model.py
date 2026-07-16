"""IsolationForest anomaly layer.

Trained at startup on a generated benign-only batch day (seeded, seconds),
persisted to disk. score(entity) → 0–40, min-max scaled against the benign score
distribution. ML alone can never fire an alert (0.35 × 100 = 35 < 60) and is only
consulted once rules reach ML_MIN_POINTS — it sharpens confirmed suspicions.
Degrades gracefully: any failure ⇒ ml_score = 0 and rules carry the demo alone.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from ..generator.world import World
from ..schemas import AuthLogin, Event, Txn
from .features import FeatureTracker, N_FEATURES

log = logging.getLogger("sutra.ml")

MODEL_VERSION = 3  # bump to invalidate persisted models


class MLScorer:
    def __init__(self, world: World, seed: int) -> None:
        self.world = world
        self.seed = seed
        self.tracker = FeatureTracker(world)
        self.model = None
        self.p_lo: float = 0.0
        self.p_med: float = 0.0
        self.ready = False

    # ------------------------------------------------------------------ runtime

    def observe(self, ev: Event) -> None:
        self.tracker.observe(ev)

    def score(self, entity_id: str, now: datetime) -> float:
        """0 (benign) .. 40 (extreme anomaly)."""
        if not self.ready:
            return 0.0
        try:
            v = np.asarray([self.tracker.vector(entity_id, now)])
            s = float(self.model.decision_function(v)[0])
            span = max(self.p_med - self.p_lo, 1e-9)
            return float(np.clip(40.0 * (self.p_med - s) / span, 0.0, 40.0))
        except Exception:  # noqa: BLE001 — never let ML break the pipeline
            log.exception("ml scoring failed; returning 0")
            return 0.0

    # ------------------------------------------------------------------ training

    def train(self, events: list[Event]) -> None:
        try:
            from sklearn.ensemble import IsolationForest
            rng = random.Random(self.seed ^ 0x111)
            tracker = FeatureTracker(self.world)
            samples: list[list[float]] = []
            staff_ids = list(self.world.staff)
            for ev in events:
                tracker.observe(ev)
                if isinstance(ev, (Txn, AuthLogin)) and rng.random() < 0.08:
                    samples.append(tracker.vector(ev.customer_id, ev.ts))
                    if rng.random() < 0.05:
                        samples.append(tracker.vector(rng.choice(staff_ids), ev.ts))
            X = np.asarray(samples)
            if len(X) < 500:
                raise RuntimeError(f"too few training samples: {len(X)}")
            model = IsolationForest(n_estimators=150, max_samples=512,
                                    contamination="auto", random_state=self.seed)
            model.fit(X)
            scores = model.decision_function(X)
            self.model = model
            self.p_lo = float(np.percentile(scores, 0.5))
            self.p_med = float(np.percentile(scores, 50))
            self.ready = True
            log.info("ML trained on %d benign vectors (p_lo=%.4f p_med=%.4f)",
                     len(X), self.p_lo, self.p_med)
        except Exception:  # noqa: BLE001
            log.exception("ML training failed — degrading to ml_score=0")
            self.ready = False

    # ------------------------------------------------------------------ persistence

    def save(self, data_dir: Path) -> None:
        if not self.ready:
            return
        try:
            import joblib
            d = data_dir / "ml"
            d.mkdir(parents=True, exist_ok=True)
            joblib.dump({"version": MODEL_VERSION, "seed": self.seed,
                         "model": self.model, "p_lo": self.p_lo, "p_med": self.p_med},
                        d / "model.joblib")
        except Exception:  # noqa: BLE001
            log.exception("could not persist ML model")

    def load(self, data_dir: Path) -> bool:
        try:
            import joblib
            path = data_dir / "ml" / "model.joblib"
            if not path.exists():
                return False
            blob = joblib.load(path)
            if blob.get("version") != MODEL_VERSION or blob.get("seed") != self.seed:
                return False
            self.model = blob["model"]
            self.p_lo, self.p_med = blob["p_lo"], blob["p_med"]
            self.ready = True
            return True
        except Exception:  # noqa: BLE001
            log.exception("could not load persisted ML model")
            return False


def train_or_load(world: World, seed: int, data_dir: Optional[Path],
                  training_events: Optional[list[Event]] = None) -> MLScorer:
    """Standard startup path: load persisted model or train on a benign day."""
    scorer = MLScorer(world, seed)
    if data_dir is not None and scorer.load(data_dir):
        log.info("ML model loaded from disk")
        return scorer
    if training_events is None:
        from ..generator.replay import batch_events
        training_events = batch_events(world, seed, hours=24.0,
                                       include_borderline=False, scenarios=())
    scorer.train(training_events)
    if data_dir is not None:
        scorer.save(data_dir)
    return scorer
