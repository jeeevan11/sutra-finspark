"""Evidence-chain narratives.

Deliberate trust decision (see ARCHITECTURE.md): narratives are Jinja templates,
not an LLM — deterministic, offline, hallucination-proof. One template per
dominant pattern, filled from the incident's actual hits and events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from jinja2 import Environment

from .config import ist
from .generator.world import World
from .rules.engine import Hit
from .schemas import (AuthLogin, EdrAlert, Event, PayeeAdded, TlsSession, Txn, inr)

_env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)

TEMPLATES = {
    "ato": _env.from_string(
        "Between {{start}} and {{end}} IST, account {{account}} ({{customer}}) was "
        "accessed from previously unseen device {{device}} on network {{asn}} "
        "({{geo}})"
        "{% if has_burst %}, minutes after a credential-stuffing burst of "
        "{{fail_count}} failed logins from the same network hit {{fail_accounts}} "
        "accounts{% endif %}"
        "{% if payee %}. The session immediately added never-seen payee {{payee}}"
        "{% endif %}"
        "{% if n_txn %}{% if has_structuring %} and sent {{n_txn}} {{txn_kind}} "
        "transfers of {{txn_amounts}} ({{txn_total}} total) — a structuring pattern "
        "designed to stay under the ₹50,000 reporting threshold{% else %} and moved "
        "{{txn_total}} in {{n_txn}} transfers{% endif %}{% endif %}."
        "{% if velocity %} One-hour outflow is {{velocity}}× this customer's 30-day "
        "daily average.{% endif %}"
        " Recommended: hold outgoing transactions and force step-up "
        "re-authentication."
    ),
    "terminal_compromise": _env.from_string(
        "At {{edr_time}} IST, branch terminal {{terminal}} raised a {{edr_sev}}-"
        "severity EDR alert ({{malware}}). {{gap}} minutes later, the same terminal "
        "initiated a {{txn_kind}} of {{amount}} from {{account}}"
        "{% if dormant %} — an account dormant for over 90 days —{% endif %} to "
        "unknown payee {{payee}}, keyed by {{staff}} at {{txn_time}} IST"
        "{% if off_hours %}, outside their baseline working hours{% endif %}. "
        "Individually each signal scores low; correlated, they indicate an attacker "
        "operating a compromised branch terminal. Recommended: hold the transaction "
        "and isolate the terminal."
    ),
    "quantum_exfil": _env.from_string(
        "Between {{start}} and {{end}} IST, server {{server}} moved {{gb}} GB in "
        "{{n_sessions}} TLS {{tls_version}} sessions using quantum-vulnerable "
        "{{kex}} key exchange to unknown destination {{dst}}. Data encrypted with "
        "{{kex}} can be harvested today and decrypted once a cryptographically "
        "relevant quantum computer exists (harvest-now-decrypt-later). Volume and "
        "destination profile are consistent with bulk exfiltration. Recommended: "
        "block the destination and rotate {{server}} to hybrid post-quantum key "
        "exchange."
    ),
    "generic": _env.from_string(
        "Between {{start}} and {{end}} IST, correlated risk activity was observed "
        "on {{entity}}: {{rule_summary}}. Review the evidence chain for the "
        "contributing events."
    ),
}


def guess_pattern(rule_ids: set[str]) -> str:
    if "R8" in rule_ids:
        return "quantum_exfil"
    if "R6" in rule_ids:
        return "terminal_compromise"
    if ("R2" in rule_ids or "R1" in rule_ids) and (
            "R4" in rule_ids or "R3" in rule_ids or "R5" in rule_ids):
        return "ato"
    return "generic"


TITLES = {
    "ato": "Account takeover with structuring — {entity}",
    "terminal_compromise": "Compromised terminal, high-value transfer — {entity}",
    "quantum_exfil": "HNDL exfiltration over vulnerable TLS — {entity}",
    "generic": "Correlated risk activity — {entity}",
}


def _fmt(ts: datetime) -> str:
    return ist(ts).strftime("%H:%M")


def build_narrative(pattern: str, entity_id: str, hits: list[Hit],
                    events: list[Event], world: World) -> str:
    """events are the incident's evidence events, time-ordered."""
    rule_ids = {h.rule_id for h in hits}
    start, end = events[0].ts, events[-1].ts
    ctx: dict = {"start": _fmt(start), "end": _fmt(end), "entity": entity_id}

    logins_ok = [e for e in events if isinstance(e, AuthLogin) and e.success]
    fails = [e for e in events if isinstance(e, AuthLogin) and not e.success]
    txns = [e for e in events if isinstance(e, Txn)]
    payees = [e for e in events if isinstance(e, PayeeAdded)]
    edrs = [e for e in events if isinstance(e, EdrAlert)]
    tls = [e for e in events if isinstance(e, TlsSession)]

    if pattern == "ato":
        login = logins_ok[-1] if logins_ok else None
        band = [t for t in txns if 45_000 <= t.amount < 50_000]
        story_txns = band if ("R4" in rule_ids and band) else txns
        ctx.update({
            "account": txns[0].account_id if txns else (login.account_id if login else entity_id),
            "customer": login.customer_id if login else entity_id,
            "device": login.device_id if login else "unknown",
            "asn": login.asn if login else "unknown",
            "geo": login.geo if login else "unknown",
            "has_burst": "R1" in rule_ids,
            "fail_count": next((h.detail.split(" ")[0] for h in hits if h.rule_id == "R1"), len(fails)),
            "fail_accounts": next((h.detail.split("across ")[1].split(" ")[0]
                                   for h in hits if h.rule_id == "R1" and "across " in h.detail), "several"),
            "payee": payees[-1].payee_id if payees else "",
            "n_txn": len(story_txns),
            "has_structuring": "R4" in rule_ids and bool(band),
            "txn_kind": story_txns[0].txn_type if story_txns else "UPI",
            "txn_amounts": inr(story_txns[0].amount) if story_txns else "",
            "txn_total": inr(sum(t.amount for t in story_txns)) if story_txns else "",
            "velocity": next((h.detail.split("is ")[1].split("×")[0]
                              for h in hits if h.rule_id == "R5" and "is " in h.detail), ""),
        })
    elif pattern == "terminal_compromise":
        edr = edrs[-1] if edrs else None
        txn = next((t for t in txns if t.terminal_id), txns[-1] if txns else None)
        gap = int((txn.ts - edr.ts).total_seconds() / 60) if (edr and txn) else 0
        dormant = "R9" in rule_ids
        ctx.update({
            "edr_time": _fmt(edr.ts) if edr else _fmt(start),
            "terminal": edr.terminal_id if edr else entity_id,
            "edr_sev": edr.severity if edr else "medium",
            "malware": edr.malware_family if edr else "unknown",
            "gap": gap,
            "txn_kind": txn.txn_type if txn else "RTGS",
            "amount": inr(txn.amount) if txn else "",
            "account": txn.account_id if txn else "",
            "dormant": dormant,
            "payee": txn.payee_id if txn else "",
            "staff": txn.staff_id if txn else "",
            "txn_time": _fmt(txn.ts) if txn else "",
            "off_hours": "R7" in rule_ids or "S7" in rule_ids,
        })
    elif pattern == "quantum_exfil":
        total = sum(s.bytes_out for s in tls)
        ctx.update({
            "server": tls[0].src if tls else entity_id,
            "gb": f"{total / 1e9:.1f}",
            "n_sessions": len(tls),
            "tls_version": tls[0].tls_version if tls else "1.2",
            "kex": tls[0].key_exchange if tls else "RSA-2048",
            "dst": tls[0].dst_ip if tls else "unknown",
        })
    else:
        names = sorted({f"{h.rule_id} ({h.name})" for h in hits})
        ctx["rule_summary"] = ", ".join(names)

    return TEMPLATES[pattern].render(**ctx)
