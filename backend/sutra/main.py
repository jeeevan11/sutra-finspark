"""SUTRA backend: one process, asyncio tasks — bus consumer + scoring + API + WS.

Boot: build the seeded world, load/train the ML model, generate PQC keys, start
FastAPI. The live replay is idle until POST /api/replay/start (or `make demo`).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .actions import ActionAdapter
from .api import router
from .bus import make_bus
from .fusion import FusionEngine
from .generator.replay import LiveReplay
from .generator.world import build_world
from .graph import EntityGraph
from .ml.model import train_or_load
from .pqc import AlertSigner
from .quantum import QuantumMonitor
from .rules.engine import RuleEngine
from .schemas import entity_refs, event_stream, event_summary
from .store import AlertStore
from .ws import WSHub

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("sutra")


class Runtime:
    """Everything the API needs, rebuildable on demo reset."""

    def __init__(self, bus, hub: WSHub) -> None:
        self.seed = config.SEED
        self.bus = bus
        self.hub = hub
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.world = build_world(self.seed)
        log.info("world built (seed=%d): %d customers, %d staff",
                 self.seed, len(self.world.customers), len(self.world.staff))
        self.ml = train_or_load(self.world, self.seed, config.DATA_DIR)
        self.signer = AlertSigner(config.DATA_DIR)
        self.store = AlertStore(str(config.DATA_DIR / "sutra.db"))
        # each boot is a fresh demo session: clean alert log, fresh chain
        self.store.wipe()
        self.replay: LiveReplay | None = None
        self._fresh_detection()

    def _fresh_detection(self) -> None:
        self.graph = EntityGraph()
        self.engine = RuleEngine(self.world, "fused")
        self.quantum = QuantumMonitor(self.world)
        self.fusion = FusionEngine(self.world, self.engine, self.graph, ml=self.ml,
                                   quantum=self.quantum, signer=self.signer,
                                   store=self.store)
        self.actions = ActionAdapter(
            self.fusion, clock=lambda: self.replay.sim_now if self.replay else None)
        self.replay = LiveReplay(self.world, self.seed, emit=self.bus.publish)

    async def reset(self) -> None:
        """Wipe alerts + graph, restart the world from seed (replay left stopped)."""
        if self.replay is not None:
            await self.replay.stop()
        # retire the current engine so any action still in flight against it aborts
        # instead of writing into the store we are about to wipe
        if getattr(self, "fusion", None) is not None:
            self.fusion.active = False
        await asyncio.sleep(0.3)  # let in-flight bus events drain
        self.store.wipe()
        self.signer.reset_chain()
        self.ml.reset_windows()
        self._fresh_detection()
        log.info("demo reset: world restarted from seed %d", self.seed)


async def _consume(app: FastAPI) -> None:
    bus, hub = app.state.bus, app.state.hub
    async for ev in bus.consume():
        rt = app.state.rt
        try:
            notes = rt.fusion.ingest(ev)
        except Exception:  # noqa: BLE001 — one bad event must not kill the stream
            log.exception("ingest failed for %s", getattr(ev, "event_id", "?"))
            continue
        hub.push_event({
            "kind": "event", "event_id": ev.event_id, "ts": ev.ts.isoformat(),
            "type": ev.type, "stream": event_stream(ev),
            "summary": event_summary(ev), "entity_refs": entity_refs(ev),
        })
        for kind, alert in notes:
            hub.push_alert({"kind": kind, "alert": alert.summary_dict()})


async def _hot_reload_rules(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(5)
        try:
            if app.state.rt.engine.maybe_reload():
                log.info("rules.yaml reloaded")
        except Exception:  # noqa: BLE001
            log.exception("rules hot-reload failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub = WSHub()
    bus = make_bus(config.BUS_MODE, config.REDIS_URL)
    app.state.hub = hub
    app.state.bus = bus
    app.state.rt = Runtime(bus, hub)
    consumer = asyncio.create_task(_consume(app), name="bus-consumer")
    reloader = asyncio.create_task(_hot_reload_rules(app), name="rules-reload")
    log.info("SUTRA backend ready (bus=%s)", config.BUS_MODE)
    try:
        yield
    finally:
        for t in (consumer, reloader):
            t.cancel()
        if app.state.rt.replay is not None:
            await app.state.rt.replay.stop()
        await bus.close()


app = FastAPI(title="SUTRA", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    await ws.app.state.hub.serve_events(ws)


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket) -> None:
    await ws.app.state.hub.serve_alerts(ws)
