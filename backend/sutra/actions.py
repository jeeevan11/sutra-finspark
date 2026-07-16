"""Mock core-banking adapter: hold / step-up / dismiss with simulated latency.

Actions update the alert status, append a signed action record to the evidence
chain, and re-sign the alert — the response itself becomes tamper-evident.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable, Optional

from .fusion import FusionEngine
from .schemas import ActionRecord, EvidenceItem, inr

LATENCY_S = 0.3

_STATUS = {"hold": "held", "stepup": "stepup", "dismiss": "dismissed"}


class ActionAdapter:
    def __init__(self, fusion: FusionEngine,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self.fusion = fusion
        self.clock = clock  # sim-time source so action records match the sim clock
        self._n = 0

    async def apply(self, alert_id: str, action: str) -> dict:
        alert = self.fusion.alerts.get(alert_id)
        if alert is None:
            raise KeyError(alert_id)
        if action not in _STATUS:
            raise ValueError(action)
        await asyncio.sleep(LATENCY_S)  # simulated core-banking round trip

        txn_items = [e for e in alert.evidence if e.type == "txn"]
        accounts = sorted({e.detail.get("account_id") for e in txn_items
                           if e.detail.get("account_id")})
        total = sum(e.detail.get("amount", 0) or 0 for e in txn_items)
        if action == "hold":
            result = (f"{len(txn_items)} transaction(s) totalling {inr(total)} held on "
                      f"{', '.join(accounts) if accounts else alert.entity_id}")
        elif action == "stepup":
            result = f"step-up re-authentication forced for {alert.entity_id}"
        else:
            result = "alert dismissed by analyst"

        now = self.clock() if self.clock is not None else datetime.now(timezone.utc)
        self._n += 1
        alert.status = _STATUS[action]
        alert.updated_ts = now
        alert.actions.append(ActionRecord(action=action, ts=now, result=result))
        alert.evidence.append(EvidenceItem(
            event_id=f"ACT-{self._n:04d}", ts=now, type="action",
            summary=f"[{action.upper()}] {result}", entity_refs=[alert.entity_id],
            rule_ids=[], detail={"action": action},
        ))
        if self.fusion.signer is not None:
            self.fusion.signer.sign_alert(alert)
        if self.fusion.store is not None:
            self.fusion.store.append_record(alert)
        return {"ok": True, "alert_id": alert_id, "action": action,
                "status": alert.status, "result": result}
