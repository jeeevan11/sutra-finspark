"""Event bus: Redis Streams (consumer group `sutra-core`) with an in-process
fallback (`SUTRA_BUS=memory`) so tests and Redis-less dev work identically.

Scaling story: the stream maps 1:1 onto a Kafka topic partitioned by entity —
the consumer is already a group member, so adding workers is a config change.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from .schemas import Event, parse_event, wire_dict

STREAM = "sutra:events"
GROUP = "sutra-core"
CONSUMER = "core-1"


class MemoryBus:
    def __init__(self) -> None:
        self.q: asyncio.Queue = asyncio.Queue(maxsize=10_000)

    async def publish(self, ev: Event) -> None:
        await self.q.put(wire_dict(ev, keep_label=True))

    async def consume(self) -> AsyncIterator[Event]:
        while True:
            d = await self.q.get()
            yield parse_event(d)

    async def close(self) -> None:
        return None


class RedisBus:
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis
        self.r = aioredis.from_url(url, decode_responses=True)
        self._group_ready = False

    async def _ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self.r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001 — BUSYGROUP = already exists
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    async def publish(self, ev: Event) -> None:
        await self.r.xadd(STREAM, {"j": json.dumps(wire_dict(ev, keep_label=True))},
                          maxlen=200_000, approximate=True)

    async def consume(self) -> AsyncIterator[Event]:
        await self._ensure_group()
        while True:
            resp = await self.r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"},
                                           count=200, block=250)
            for _stream, entries in resp or []:
                for entry_id, fields in entries:
                    try:
                        yield parse_event(json.loads(fields["j"]))
                    finally:
                        await self.r.xack(STREAM, GROUP, entry_id)

    async def close(self) -> None:
        await self.r.aclose()


def make_bus(mode: str, redis_url: str):
    return RedisBus(redis_url) if mode == "redis" else MemoryBus()
