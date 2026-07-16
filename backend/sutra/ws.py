"""WebSocket hub: /ws/events (throttled ~30 msg/s, drop-oldest) and /ws/alerts."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

EVENTS_PER_TICK = 3     # 3 msgs / 100ms tick = 30 msg/s per client
TICK_S = 0.1
BUFFER = 120            # drop-oldest beyond this


class WSHub:
    def __init__(self) -> None:
        self._event_queues: dict[WebSocket, deque] = {}
        self._alert_queues: dict[WebSocket, deque] = {}

    # ------------------------------------------------------------------ producers

    def push_event(self, payload: dict[str, Any]) -> None:
        msg = json.dumps(payload)
        for q in self._event_queues.values():
            q.append(msg)  # deque(maxlen) drops oldest automatically

    def push_alert(self, payload: dict[str, Any]) -> None:
        msg = json.dumps(payload)
        for q in self._alert_queues.values():
            q.append(msg)

    # ------------------------------------------------------------------ consumers

    async def serve_events(self, ws: WebSocket) -> None:
        await ws.accept()
        q: deque = deque(maxlen=BUFFER)
        self._event_queues[ws] = q
        try:
            while True:
                sent = 0
                while q and sent < EVENTS_PER_TICK:
                    await ws.send_text(q.popleft())
                    sent += 1
                await asyncio.sleep(TICK_S)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self._event_queues.pop(ws, None)

    async def serve_alerts(self, ws: WebSocket) -> None:
        await ws.accept()
        q: deque = deque(maxlen=BUFFER)
        self._alert_queues[ws] = q
        try:
            while True:
                while q:
                    await ws.send_text(q.popleft())
                await asyncio.sleep(TICK_S)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self._alert_queues.pop(ws, None)
