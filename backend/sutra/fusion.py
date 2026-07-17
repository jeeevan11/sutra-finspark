"""Risk fusion, incident correlation, alert lifecycle.

Incidents are entity-SET scoped: a hit joins any open incident it shares an entity
with, so a credential-stuffing burst, the takeover login, the mule payee and the
structuring txns all merge into ONE alert. risk = min(100, 0.65·Σpoints + 0.35·(ml·2.5)),
alert at ≥60, risk only ratchets up (max) on update, 45-minute rolling window.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from .config import (ALERT_THRESHOLD, INCIDENT_WINDOW_MIN, ML_MIN_POINTS, ML_WEIGHT,
                     RULE_WEIGHT, SILOED_THRESHOLD, severity_for)
from .explain import MITRE_TAGS, TITLES, build_narrative, guess_pattern
from .generator.world import World
from .graph import EntityGraph
from .rules.engine import Hit, RuleEngine
from .schemas import (Alert, EvidenceItem, Event, RuleHitModel, TlsSession,
                      entity_type_of, event_summary, entity_refs)

_TYPE_PRIORITY = ["customer", "staff", "terminal", "server", "account", "device",
                  "payee", "asn", "ip"]


class Incident:
    __slots__ = ("entities", "hits", "event_order", "ml_score", "created_ts",
                 "last_ts", "alert_id", "labels")

    def __init__(self, ts: datetime) -> None:
        self.entities: set[str] = set()
        self.hits: dict[str, Hit] = {}          # dedup_key -> first Hit
        self.event_order: dict[str, None] = {}  # ordered set of event ids
        self.ml_score: float = 0.0
        self.created_ts = ts
        self.last_ts = ts
        self.alert_id: Optional[str] = None
        self.labels: Counter = Counter()

    def points(self) -> int:
        return sum(h.points for h in self.hits.values())

    def rule_ids(self) -> set[str]:
        return {h.rule_id for h in self.hits.values()}


class FusionEngine:
    def __init__(self, world: World, engine: RuleEngine, graph: EntityGraph,
                 ml=None, quantum=None, signer=None, store=None) -> None:
        self.world = world
        self.engine = engine
        self.graph = graph
        self.ml = ml
        self.quantum = quantum
        self.signer = signer
        self.store = store
        self.incidents: list[Incident] = []
        self.alerts: dict[str, Alert] = {}
        self.alert_labels: dict[str, Counter] = {}  # benchmark ground-truth bookkeeping
        self._seq = 0
        self._merge_notes: list[tuple[str, Alert]] = []
        # False once a demo reset retires this engine — an action still in flight
        # (300ms latency) against the old engine must not write into the wiped
        # store / reset chain. See ActionAdapter.apply.
        self.active = True

    # ------------------------------------------------------------------ ingest

    def ingest(self, ev: Event) -> list[tuple[str, Alert]]:
        """Returns [(kind, alert)] notifications ("alert_created"/"alert_updated")."""
        if self.quantum is not None and isinstance(ev, TlsSession):
            self.quantum.observe(ev)
        if self.ml is not None:
            self.ml.observe(ev)
        self.graph.ingest(ev)
        hits = self.engine.observe(ev)
        if not hits:
            return []
        self._prune(ev.ts)
        touched: list[Incident] = []
        for hit in hits:
            inc = self._route(hit)
            self._apply(inc, hit)
            if inc not in touched:
                touched.append(inc)
        out: list[tuple[str, Alert]] = self._merge_notes
        self._merge_notes = []
        for inc in touched:
            note = self._score_and_alert(inc, ev.ts)
            if note is not None:
                out.append(note)
        return out

    # ------------------------------------------------------------------ internals

    def _prune(self, now: datetime) -> None:
        horizon = timedelta(minutes=INCIDENT_WINDOW_MIN)
        self.incidents = [i for i in self.incidents if now - i.last_ts <= horizon]

    def _route(self, hit: Hit) -> Incident:
        ents = set(hit.entities)
        matches = [i for i in self.incidents if i.entities & ents]
        if not matches:
            inc = Incident(hit.ts)
            self.incidents.append(inc)
            return inc
        primary = matches[0]
        for other in matches[1:]:
            primary.entities |= other.entities
            for k, h in other.hits.items():
                primary.hits.setdefault(k, h)
            primary.event_order.update(other.event_order)
            primary.labels.update(other.labels)
            primary.ml_score = max(primary.ml_score, other.ml_score)
            primary.created_ts = min(primary.created_ts, other.created_ts)
            if primary.alert_id is None:
                primary.alert_id = other.alert_id
            elif other.alert_id is not None and other.alert_id != primary.alert_id:
                # both sides already alerted: consolidate — retire the absorbed
                # alert visibly instead of orphaning it open at a stale risk
                dead = self.alerts.get(other.alert_id)
                if dead is not None and dead.status != "dismissed":
                    dead.status = "dismissed"
                    dead.narrative = (f"[Merged into {primary.alert_id} — this "
                                      f"incident correlated with a wider campaign] "
                                      + dead.narrative)
                    dead.updated_ts = max(dead.updated_ts, hit.ts)
                    if self.signer is not None:
                        self.signer.sign_alert(dead)
                    if self.store is not None:
                        self.store.append_record(dead)
                    self._merge_notes.append(("alert_updated", dead))
            self.incidents.remove(other)
        return primary

    def _apply(self, inc: Incident, hit: Hit) -> None:
        inc.entities |= set(hit.entities)
        inc.last_ts = max(inc.last_ts, hit.ts)
        existing = inc.hits.get(hit.dedup_key)
        if existing is None:
            inc.hits[hit.dedup_key] = hit
            new_event_ids = hit.event_ids
        else:
            # same logical hit, growing evidence (e.g. a 4th structuring txn)
            merged = list(dict.fromkeys(existing.event_ids + hit.event_ids))
            existing.event_ids = merged
            existing.detail = hit.detail
            new_event_ids = hit.event_ids
        for eid in new_event_ids:
            if eid not in inc.event_order:
                inc.event_order[eid] = None
                ev = self.graph.get_event(eid)
                if ev is not None and ev.scenario:
                    inc.labels[ev.scenario] += 1

    def _primary_entity(self, inc: Incident, pattern: str) -> str:
        if pattern == "terminal_compromise":
            for h in inc.hits.values():
                if h.rule_id == "R6":
                    return h.entities[0]
        if pattern == "quantum_exfil":
            for h in inc.hits.values():
                if h.rule_id == "R8":
                    return h.entities[0]
        pts: dict[str, int] = {}
        for h in inc.hits.values():
            for e in h.entities:
                pts[e] = pts.get(e, 0) + h.points
        if pattern == "ato":
            custs = {e: p for e, p in pts.items() if entity_type_of(e) == "customer"}
            if custs:
                return max(custs, key=lambda e: custs[e])
        def rank(e: str) -> tuple:
            t = entity_type_of(e)
            pri = _TYPE_PRIORITY.index(t) if t in _TYPE_PRIORITY else 99
            return (-pts[e], pri, e)
        return min(pts, key=rank)

    def _score_and_alert(self, inc: Incident, now: datetime) -> Optional[tuple[str, Alert]]:
        points = inc.points()
        if points >= ML_MIN_POINTS and self.ml is not None:
            cands = [e for e in inc.entities
                     if entity_type_of(e) in ("customer", "staff")]
            if cands:
                score = max(self.ml.score(e, now) for e in cands)
                inc.ml_score = max(inc.ml_score, score)
        risk = min(100, round(RULE_WEIGHT * points + ML_WEIGHT * inc.ml_score * 2.5))
        if risk < ALERT_THRESHOLD and inc.alert_id is None:
            return None

        hits = sorted(inc.hits.values(), key=lambda h: h.ts)
        rule_ids = inc.rule_ids()
        pattern = guess_pattern(rule_ids)
        primary = self._primary_entity(inc, pattern)
        events = [self.graph.get_event(eid) for eid in inc.event_order]
        events = [e for e in events if e is not None]
        events.sort(key=lambda e: (e.ts, e.event_id))
        ev_rules: dict[str, list[str]] = {}
        for h in hits:
            for eid in h.event_ids:
                ev_rules.setdefault(eid, [])
                if h.rule_id not in ev_rules[eid]:
                    ev_rules[eid].append(h.rule_id)

        evidence = [EvidenceItem(
            event_id=e.event_id, ts=e.ts, type=e.type, summary=event_summary(e),
            entity_refs=entity_refs(e), rule_ids=ev_rules.get(e.event_id, []),
            detail=e.model_dump(mode="json", exclude={"event_id", "ts", "type", "scenario"}),
        ) for e in events]
        narrative = build_narrative(pattern, primary, hits, events, self.world)
        rule_hits = [RuleHitModel(rule_id=h.rule_id, name=h.name, domain=h.domain,
                                  points=h.points, detail=h.detail, ts=h.ts)
                     for h in hits]
        tags = ["quantum"] if any(h.domain == "quantum" for h in hits) else []
        tags += MITRE_TAGS.get(pattern, [])

        if inc.alert_id is None:
            self._seq += 1
            alert = Alert(
                alert_id=f"ALT-{self._seq:04d}", created_ts=now, updated_ts=now,
                entity_type=entity_type_of(primary), entity_id=primary, risk=risk,
                severity=severity_for(risk), title=TITLES[pattern].format(entity=primary),
                scenario_guess=pattern, tags=tags, narrative=narrative,
                evidence=evidence, rule_hits=rule_hits, ml_score=round(inc.ml_score, 1),
            )
            inc.alert_id = alert.alert_id
            self.alerts[alert.alert_id] = alert
            self.alert_labels[alert.alert_id] = inc.labels
            kind = "alert_created"
        else:
            alert = self.alerts[inc.alert_id]
            new_risk = max(alert.risk, risk)
            # Compare like with like: `evidence` holds only detection events, but
            # alert.evidence also carries any operator-action items (hold/stepup).
            # Count non-action items on both sides, else an applied action skews
            # the guard — dropping a genuine new-evidence update, or re-signing on
            # every subsequent hit.
            prior_event_count = sum(1 for i in alert.evidence if i.type != "action")
            if (new_risk == alert.risk and len(evidence) == prior_event_count
                    and alert.ml_score == round(inc.ml_score, 1)):
                return None  # nothing meaningful changed
            alert.risk = new_risk
            alert.severity = severity_for(new_risk)
            alert.updated_ts = now
            alert.entity_id = primary
            alert.entity_type = entity_type_of(primary)
            alert.title = TITLES[pattern].format(entity=primary)
            alert.scenario_guess = pattern
            alert.tags = tags
            alert.narrative = narrative
            alert.evidence = evidence + [
                i for i in alert.evidence if i.type == "action"]
            alert.rule_hits = rule_hits
            alert.ml_score = round(inc.ml_score, 1)
            kind = "alert_updated"

        if self.signer is not None:
            self.signer.sign_alert(alert)
        if self.store is not None:
            self.store.append_record(alert)
        return (kind, alert)

    # ------------------------------------------------------------------ queries

    def open_alert_counts(self) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0}
        for a in self.alerts.values():
            if a.status == "open":
                counts[a.severity] = counts.get(a.severity, 0) + 1
        return counts

    def held_txn_count(self) -> int:
        n = 0
        for a in self.alerts.values():
            if a.status == "held":
                n += sum(1 for e in a.evidence if e.type == "txn")
        return n


class SiloedFusion:
    """Models today's separate SIEM + FRM stack (benchmark only): per-domain
    incidents anchored on a single entity, 25-point threshold, no cross-domain
    context, no quantum monitoring, no ML."""

    def __init__(self, world: World, engine: RuleEngine) -> None:
        self.world = world
        self.engine = engine
        self.incidents: dict[tuple[str, str], dict] = {}
        self.alerts: list[dict] = []

    def ingest(self, ev: Event) -> None:
        hits = self.engine.observe(ev)
        for hit in hits:
            key = (hit.domain, hit.entities[0])
            inc = self.incidents.get(key)
            if inc is None or (hit.ts - inc["last_ts"]) > timedelta(minutes=INCIDENT_WINDOW_MIN):
                inc = {"points": 0, "hits": {}, "event_ids": {}, "labels": Counter(),
                       "created_ts": hit.ts, "last_ts": hit.ts, "alert": None}
                self.incidents[key] = inc
            if hit.dedup_key not in inc["hits"]:
                inc["hits"][hit.dedup_key] = hit
                inc["points"] += hit.points
            inc["last_ts"] = hit.ts
            for eid in hit.event_ids:
                inc["event_ids"][eid] = None
            if ev.scenario:
                inc["labels"][ev.scenario] += 1
            if inc["points"] >= SILOED_THRESHOLD:
                if inc["alert"] is None:
                    inc["alert"] = {
                        "domain": hit.domain, "entity": hit.entities[0],
                        "created_ts": hit.ts, "points": inc["points"],
                        "labels": inc["labels"], "rule_ids": set(),
                    }
                    self.alerts.append(inc["alert"])
                inc["alert"]["points"] = max(inc["alert"]["points"], inc["points"])
                inc["alert"]["rule_ids"] = {h.rule_id for h in inc["hits"].values()}
