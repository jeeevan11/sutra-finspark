"""Replay engine: batch mode (benchmark/export) and live mode (demo).

Live mode runs a simulated clock decoupled from wall time: sim_now advances by
wall_dt × speed. Scenarios inject on demand relative to sim_now. Determinism:
all randomness comes from seeded Random instances; same seed + same injections
⇒ same events ⇒ same alerts.
"""

from __future__ import annotations

import asyncio
import heapq
import random
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional

from ..config import BATCH_SIM_START, LIVE_SIM_START
from ..schemas import Event
from .noise import IdSource, NoiseGenerator
from .scenarios import SCENARIOS, borderline_events
from .world import World

# Fixed scenario offsets in the batch day (hours from 00:00 IST).
BATCH_SCENARIO_OFFSETS_H = {"A": 10.0, "B": 22.55, "C": 18.0}  # B txn lands 22:40 IST


def batch_events(world: World, seed: int, hours: float = 24.0,
                 include_noise: bool = True, include_borderline: bool = True,
                 scenarios: tuple[str, ...] = ("A", "B", "C"),
                 start: datetime = BATCH_SIM_START) -> list[Event]:
    """Full simulated window, ground-truth labels preserved, sorted by ts."""
    ids = IdSource()
    events: list[Event] = []
    if include_noise:
        gen = NoiseGenerator(world, random.Random(seed ^ 0x0110_15E), ids)
        for m in range(int(hours * 60)):
            events.extend(gen.minute(start + timedelta(minutes=m)))
    if include_borderline:
        events.extend(borderline_events(world, start, random.Random(seed ^ 0xB0DE), ids))
    s_rng = random.Random(seed ^ 0x5CEA)
    for name in scenarios:
        t0 = start + timedelta(hours=BATCH_SCENARIO_OFFSETS_H[name])
        events.extend(SCENARIOS[name](world, t0, s_rng, ids))
    events.sort(key=lambda e: (e.ts, e.event_id))
    return events


class LiveReplay:
    """Continuous benign noise + on-demand scenario injection."""

    def __init__(self, world: World, seed: int,
                 emit: Callable[[Event], Awaitable[None]],
                 sim_start: datetime = LIVE_SIM_START) -> None:
        self.world = world
        self.seed = seed
        self.emit = emit
        self.sim_start = sim_start
        self.sim_now = sim_start
        self.speed = 20
        self.running = False
        self.paused = False
        self.events_emitted = 0
        self._ids = IdSource()
        self._noise = NoiseGenerator(world, random.Random(seed ^ 0x11FE), self._ids)
        self._scenario_rng = random.Random(seed ^ 0x5CEA)
        self._noise_cursor = sim_start          # next minute boundary to generate
        self._pending: list[tuple[datetime, str, Event]] = []  # heap by ts
        self._inject_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0}
        self._emit_wall_ts: list[float] = []    # for events/min KPI
        self._task: Optional[asyncio.Task] = None

    # ---------------------------------------------------------------- controls

    def start(self, speed: Optional[int] = None) -> None:
        if speed in (1, 5, 20):
            self.speed = speed
        self.running = True
        self.paused = False
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="live-replay")

    def ensure_running(self) -> None:
        """Start the loop if idle WITHOUT touching an operator's manual pause —
        injecting a scenario while paused must not resume the clock mid-sentence."""
        if not self.running:
            self.start()
        elif self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="live-replay")

    def pause_toggle(self) -> bool:
        """Returns new paused state."""
        if self.running:
            self.paused = not self.paused
        return self.paused

    async def stop(self) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # Live injections compress intra-scenario gaps (spec 6.4) so the full story —
    # including the critical alert — lands well inside 20s of wall clock at x20.
    LIVE_COMPRESS = 0.5

    def inject(self, name: str) -> int:
        """Schedule scenario events starting a few sim-seconds from now.
        Returns the instance number used."""
        instance = self._inject_counts[name]
        self._inject_counts[name] += 1
        t0 = self.sim_now + timedelta(seconds=5 * self.speed / 20)
        for ev in SCENARIOS[name](self.world, t0, self._scenario_rng, self._ids,
                                  instance, compress=self.LIVE_COMPRESS):
            heapq.heappush(self._pending, (ev.ts, ev.event_id, ev))
        return instance

    def events_per_min(self) -> float:
        now = time.monotonic()
        self._emit_wall_ts = [t for t in self._emit_wall_ts if now - t < 15]
        return round(len(self._emit_wall_ts) * 60 / 15, 1)

    def status(self) -> dict:
        return {
            "running": self.running,
            "paused": self.paused,
            "speed": self.speed,
            "sim_time": self.sim_now.isoformat(),
            "events_emitted": self.events_emitted,
            "events_per_min": self.events_per_min(),
            "seed": self.seed,
        }

    # ---------------------------------------------------------------- internals

    async def _loop(self) -> None:
        last_wall = time.monotonic()
        buffer: list[Event] = []
        while True:
            await asyncio.sleep(0.25)
            now_wall = time.monotonic()
            if not self.running:
                return
            if self.paused:
                last_wall = now_wall
                continue
            dt = now_wall - last_wall
            last_wall = now_wall
            self.sim_now += timedelta(seconds=dt * self.speed)

            # generate benign noise up to the sim clock
            while self._noise_cursor <= self.sim_now:
                buffer.extend(self._noise.minute(self._noise_cursor))
                self._noise_cursor += timedelta(minutes=1)
            # pull due scenario events
            while self._pending and self._pending[0][0] <= self.sim_now:
                buffer.append(heapq.heappop(self._pending)[2])

            due = [e for e in buffer if e.ts <= self.sim_now]
            if not due:
                continue
            buffer = [e for e in buffer if e.ts > self.sim_now]
            due.sort(key=lambda e: (e.ts, e.event_id))
            for ev in due:
                # live mode: strip generator-side ground-truth labels before the bus
                await self.emit(ev.model_copy(update={"scenario": ""}))
                self.events_emitted += 1
                self._emit_wall_ts.append(time.monotonic())
