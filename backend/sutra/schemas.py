"""Pydantic models for all events, alerts and evidence. Single source of truth."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

from .config import ist

# ---------------------------------------------------------------------------- events


class BaseEvent(BaseModel):
    event_id: str
    ts: datetime
    type: str
    # Generator-side ground-truth label ("benign", "A", "B", "C", "noise-<archetype>").
    # Stripped before events hit the bus in live mode; preserved in batch/benchmark mode.
    scenario: str = "benign"


class AuthLogin(BaseEvent):
    type: Literal["auth_login"] = "auth_login"
    customer_id: str
    account_id: str
    device_id: str
    ip: str
    asn: str
    geo: str
    success: bool
    channel: Literal["netbanking", "mobile"]


class EdrAlert(BaseEvent):
    type: Literal["edr_alert"] = "edr_alert"
    terminal_id: str
    staff_id: str
    malware_family: str
    severity: Literal["low", "med", "high"]


class TlsSession(BaseEvent):
    type: Literal["tls_session"] = "tls_session"
    src: str
    dst_ip: str
    dst_known: bool
    tls_version: Literal["1.2", "1.3"]
    key_exchange: Literal["RSA-2048", "ECDHE-P256", "X25519", "X25519Kyber768-hybrid"]
    bytes_out: int


class PayeeAdded(BaseEvent):
    type: Literal["payee_added"] = "payee_added"
    customer_id: str
    account_id: str
    payee_id: str
    payee_name: str
    device_id: str
    ip: str


class PasswordReset(BaseEvent):
    type: Literal["password_reset"] = "password_reset"
    customer_id: str
    device_id: str
    ip: str
    asn: str


class Txn(BaseEvent):
    type: Literal["txn"] = "txn"
    txn_id: str
    account_id: str
    customer_id: str
    txn_type: Literal["UPI", "IMPS", "NEFT", "RTGS"]
    amount: float
    payee_id: str
    payee_known: bool
    channel: Literal["netbanking", "mobile", "branch"]
    device_id: Optional[str] = None
    terminal_id: Optional[str] = None
    staff_id: Optional[str] = None
    ip: str
    geo: str


Event = Union[AuthLogin, EdrAlert, TlsSession, PayeeAdded, PasswordReset, Txn]

VULNERABLE_KEX = ("RSA-2048", "ECDHE-P256")


def entity_type_of(entity_id: str) -> str:
    for prefix, kind in (
        ("CUST-", "customer"), ("ACC-", "account"), ("DEV-", "device"),
        ("STAFF-", "staff"), ("TERM-", "terminal"), ("PAYEE-", "payee"),
        ("AS", "asn"), ("DB-", "server"), ("APP-", "server"),
    ):
        if entity_id.startswith(prefix):
            return kind
    return "ip"


def entity_refs(ev: Event) -> list[str]:
    """Every entity id an event touches (order: most-specific first)."""
    if isinstance(ev, AuthLogin):
        return [ev.customer_id, ev.account_id, ev.device_id, ev.asn, ev.ip]
    if isinstance(ev, EdrAlert):
        return [ev.terminal_id, ev.staff_id]
    if isinstance(ev, TlsSession):
        return [ev.src, ev.dst_ip]
    if isinstance(ev, PayeeAdded):
        return [ev.customer_id, ev.account_id, ev.payee_id, ev.device_id, ev.ip]
    if isinstance(ev, PasswordReset):
        return [ev.customer_id, ev.device_id, ev.asn, ev.ip]
    if isinstance(ev, Txn):
        refs = [ev.customer_id, ev.account_id, ev.payee_id]
        if ev.device_id:
            refs.append(ev.device_id)
        if ev.terminal_id:
            refs.append(ev.terminal_id)
        if ev.staff_id:
            refs.append(ev.staff_id)
        return refs
    return []


def inr(amount: float) -> str:
    """₹18,50,000 — Indian digit grouping."""
    n = int(round(amount))
    s = str(n)
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return "₹" + ",".join(parts) + "," + tail


def event_summary(ev: Event) -> str:
    """One mono-friendly line for the UI event rivers."""
    if isinstance(ev, AuthLogin):
        outcome = "OK " if ev.success else "FAIL"
        return f"login {outcome} {ev.customer_id} {ev.device_id} {ev.asn} {ev.geo} [{ev.channel}]"
    if isinstance(ev, EdrAlert):
        return f"EDR {ev.severity.upper()} {ev.terminal_id} {ev.malware_family} (staff {ev.staff_id})"
    if isinstance(ev, TlsSession):
        known = "known" if ev.dst_known else "UNKNOWN"
        mb = ev.bytes_out / 1_000_000
        return f"TLS{ev.tls_version} {ev.src} → {ev.dst_ip} ({known}) {ev.key_exchange} {mb:,.0f}MB"
    if isinstance(ev, PayeeAdded):
        return f"payee+ {ev.customer_id} added {ev.payee_id} ({ev.payee_name})"
    if isinstance(ev, PasswordReset):
        return f"pwd-reset {ev.customer_id} {ev.device_id} {ev.asn}"
    if isinstance(ev, Txn):
        payee = ev.payee_id if ev.payee_known else f"{ev.payee_id} (new)"
        via = ev.terminal_id or ev.device_id or ev.channel
        return f"{ev.txn_type} {inr(ev.amount)} {ev.account_id} → {payee} via {via}"
    return ev.type


def event_stream(ev: Event) -> str:
    return "transaction" if isinstance(ev, Txn) else "security"


def wire_dict(ev: Event, keep_label: bool = False) -> dict[str, Any]:
    d = ev.model_dump(mode="json")
    if not keep_label:
        d.pop("scenario", None)
    return d


# ---------------------------------------------------------------------------- alerts


class RuleHitModel(BaseModel):
    rule_id: str
    name: str
    domain: Literal["security", "transaction", "fused", "quantum"]
    points: int
    detail: str
    ts: datetime


class EvidenceItem(BaseModel):
    event_id: str
    ts: datetime
    type: str  # event type, or "action"
    summary: str
    entity_refs: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class ActionRecord(BaseModel):
    action: Literal["hold", "stepup", "dismiss"]
    ts: datetime
    result: str


class Alert(BaseModel):
    alert_id: str
    created_ts: datetime
    updated_ts: datetime
    entity_type: str
    entity_id: str
    risk: int
    severity: str
    status: Literal["open", "held", "stepup", "dismissed"] = "open"
    title: str
    scenario_guess: str = "generic"
    tags: list[str] = Field(default_factory=list)
    narrative: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    rule_hits: list[RuleHitModel] = Field(default_factory=list)
    ml_score: float = 0.0
    signature: str = ""
    prev_hash: str = ""
    pubkey_fingerprint: str = ""
    actions: list[ActionRecord] = Field(default_factory=list)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "risk": self.risk,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "scenario_guess": self.scenario_guess,
            "tags": self.tags,
            "evidence_count": len(self.evidence),
        }


def hhmm_ist(ts: datetime) -> str:
    return ist(ts).strftime("%H:%M")
