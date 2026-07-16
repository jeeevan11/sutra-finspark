"""Entity graph: the correlation primitive.

Every event upserts typed nodes and edges (edge carries event ref + ts).
`neighborhood(entity_id, window_minutes, now)` returns recent events touching the
entity's 1-hop neighborhood — what rules and evidence chains correlate over.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

import networkx as nx

from .schemas import (AuthLogin, EdrAlert, Event, PasswordReset, PayeeAdded,
                      TlsSession, Txn, entity_refs, entity_type_of)

MAX_EVENTS = 250_000        # ring buffer of raw events
PER_ENTITY_CAP = 3_000      # recent event refs kept per entity


def _edges_for(ev: Event) -> list[tuple[str, str, str]]:
    if isinstance(ev, AuthLogin):
        return [(ev.device_id, ev.account_id, "login"),
                (ev.asn, ev.device_id, "routes"),
                (ev.customer_id, ev.device_id, "uses"),
                (ev.customer_id, ev.account_id, "owns")]
    if isinstance(ev, EdrAlert):
        return [(ev.terminal_id, ev.staff_id, "edr")]
    if isinstance(ev, TlsSession):
        return [(ev.src, ev.dst_ip, "tls")]
    if isinstance(ev, PayeeAdded):
        return [(ev.customer_id, ev.payee_id, "added_payee"),
                (ev.device_id, ev.payee_id, "added_from")]
    if isinstance(ev, PasswordReset):
        return [(ev.device_id, ev.customer_id, "pwd_reset")]
    if isinstance(ev, Txn):
        edges = [(ev.account_id, ev.payee_id, "txn"),
                 (ev.customer_id, ev.account_id, "owns")]
        if ev.device_id:
            edges.append((ev.device_id, ev.account_id, "txn_via"))
        if ev.terminal_id:
            edges.append((ev.terminal_id, ev.account_id, "txn_via"))
        if ev.staff_id:
            edges.append((ev.staff_id, ev.terminal_id or ev.account_id, "operates"))
        return edges
    return []


class EntityGraph:
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()
        self.events: OrderedDict[str, Event] = OrderedDict()
        self.entity_events: dict[str, deque[tuple[datetime, str]]] = defaultdict(
            lambda: deque(maxlen=PER_ENTITY_CAP))

    def ingest(self, ev: Event) -> None:
        self.events[ev.event_id] = ev
        if len(self.events) > MAX_EVENTS:
            self.events.popitem(last=False)
        for ref in entity_refs(ev):
            if ref not in self.g:
                self.g.add_node(ref, type=entity_type_of(ref))
            self.entity_events[ref].append((ev.ts, ev.event_id))
        for src, dst, kind in _edges_for(ev):
            self.g.add_edge(src, dst, key=ev.event_id, type=kind,
                            ts=ev.ts.isoformat(), event_id=ev.event_id)

    def get_event(self, event_id: str) -> Optional[Event]:
        return self.events.get(event_id)

    def neighbors(self, entity_id: str) -> set[str]:
        if entity_id not in self.g:
            return set()
        return set(self.g.successors(entity_id)) | set(self.g.predecessors(entity_id))

    def neighborhood(self, entity_id: str, window_minutes: float,
                     now: datetime) -> list[Event]:
        """Recent events touching the entity or its 1-hop neighbors, time-ordered."""
        cutoff = now - timedelta(minutes=window_minutes)
        seen: set[str] = set()
        out: list[Event] = []
        for ent in {entity_id} | self.neighbors(entity_id):
            for ts, eid in self.entity_events.get(ent, ()):
                if ts >= cutoff and eid not in seen:
                    seen.add(eid)
                    ev = self.events.get(eid)
                    if ev is not None:
                        out.append(ev)
        out.sort(key=lambda e: (e.ts, e.event_id))
        return out

    def subgraph_dict(self, entity_id: str) -> Optional[dict]:
        """1-hop neighborhood for the /graph API."""
        if entity_id not in self.g:
            return None
        nodes = {entity_id} | self.neighbors(entity_id)
        node_list = [{"id": n, "type": self.g.nodes[n].get("type", "ip")} for n in sorted(nodes)]
        edges = []
        for src, dst, key, data in self.g.edges(nodes, keys=True, data=True):
            if src in nodes and dst in nodes:
                edges.append({"src": src, "dst": dst, "type": data.get("type", ""),
                              "ts": data.get("ts", ""), "event_id": data.get("event_id", "")})
        edges = edges[-400:]  # bound payload
        return {"nodes": node_list, "edges": edges}
