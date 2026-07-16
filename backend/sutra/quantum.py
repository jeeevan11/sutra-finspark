"""Quantum-risk module: crypto inventory + HNDL (harvest-now-decrypt-later) exposure.

Maintains a per-asset inventory from observed tls_session events: session counts by
key exchange, a PQC-readiness badge, and an HNDL score combining the share of
quantum-vulnerable sessions to unknown destinations with the volume moved over them.
Feeds R8 context and the /quantum page.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from .generator.world import World
from .schemas import TlsSession, VULNERABLE_KEX

WINDOW = timedelta(minutes=60)

_BADGE_RANK = {"green": 0, "amber": 1, "red": 2}


def _badge_for_kex(kex: str) -> str:
    if kex in VULNERABLE_KEX:
        return "red"
    if kex == "X25519":
        return "amber"
    return "green"


class _AssetStats:
    __slots__ = ("kex_counts", "bytes_unknown", "unknown_recent", "last_seen")

    def __init__(self) -> None:
        self.kex_counts: Counter = Counter()
        self.bytes_unknown = 0
        # (ts, bytes, vulnerable) for unknown-dst sessions in the rolling window
        self.unknown_recent: deque = deque()
        self.last_seen: Optional[datetime] = None


class QuantumMonitor:
    def __init__(self, world: World) -> None:
        self.world = world
        self.stats: dict[str, _AssetStats] = defaultdict(_AssetStats)
        for sid in world.servers:  # servers always visible in the inventory
            self.stats[sid] = _AssetStats()

    def observe(self, ev: TlsSession) -> None:
        st = self.stats[ev.src]
        st.kex_counts[ev.key_exchange] += 1
        st.last_seen = ev.ts
        if not ev.dst_known:
            st.bytes_unknown += ev.bytes_out
            st.unknown_recent.append((ev.ts, ev.bytes_out, ev.key_exchange in VULNERABLE_KEX))
            cutoff = ev.ts - WINDOW
            while st.unknown_recent and st.unknown_recent[0][0] < cutoff:
                st.unknown_recent.popleft()

    # ------------------------------------------------------------------ scoring

    def _badge(self, asset_id: str, st: _AssetStats) -> str:
        if st.kex_counts:
            return max((_badge_for_kex(k) for k in st.kex_counts), key=_BADGE_RANK.get)
        server = self.world.servers.get(asset_id)
        if server:  # declared posture until traffic is observed
            return max((_badge_for_kex(k) for k in server.kex_weights),
                       key=_BADGE_RANK.get)
        return "amber"

    def hndl_score(self, asset_id: str) -> int:
        st = self.stats.get(asset_id)
        if st is None:
            return 0
        recent = list(st.unknown_recent)
        vuln = [b for _, b, v in recent if v]
        share = len(vuln) / len(recent) if recent else 0.0
        volume = min(1.0, sum(vuln) / 1e9)
        return min(100, round(30 * share + 70 * volume))

    def inventory(self) -> list[dict]:
        out = []
        for asset_id, st in self.stats.items():
            kind = "server" if asset_id in self.world.servers else "terminal"
            out.append({
                "asset_id": asset_id,
                "kind": kind,
                "sessions_by_kex": dict(st.kex_counts),
                "pqc_ready": self._badge(asset_id, st),
                "hndl_score": self.hndl_score(asset_id),
                "bytes_to_unknown": st.bytes_unknown,
                "last_seen": st.last_seen.isoformat() if st.last_seen else None,
            })
        out.sort(key=lambda a: (a["kind"] != "server", -a["hndl_score"],
                                -_BADGE_RANK[a["pqc_ready"]], a["asset_id"]))
        return out

    def red_asset_count(self) -> int:
        return sum(1 for a in self.inventory() if a["pqc_ready"] == "red")
