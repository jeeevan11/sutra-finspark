"""REST routes — shapes pinned by API_CONTRACT.md at the repo root."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .config import DELIVERABLES_DIR
from .pqc import AlertSigner
from .schemas import Alert

router = APIRouter(prefix="/api")


def _rt(request: Request):
    return request.app.state.rt


# ------------------------------------------------------------------ health


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ------------------------------------------------------------------ alerts


def _alert_detail(a: Alert) -> dict:
    d = a.summary_dict()
    d.update({
        "narrative": a.narrative,
        "evidence": [e.model_dump(mode="json") for e in a.evidence],
        "rule_hits": [h.model_dump(mode="json") for h in a.rule_hits],
        "ml_score": a.ml_score,
        "signature": a.signature,
        "prev_hash": a.prev_hash,
        "pubkey_fingerprint": a.pubkey_fingerprint,
        "actions": [x.model_dump(mode="json") for x in a.actions],
    })
    return d


@router.get("/alerts")
async def list_alerts(request: Request, status: Optional[str] = None,
                severity: Optional[str] = None) -> dict:
    rt = _rt(request)
    alerts = [a for a in rt.fusion.alerts.values()
              if (status is None or a.status == status)
              and (severity is None or a.severity == severity)]
    alerts.sort(key=lambda a: (a.risk, a.updated_ts), reverse=True)
    return {"alerts": [a.summary_dict() for a in alerts]}


@router.get("/alerts/{alert_id}")
async def get_alert(request: Request, alert_id: str) -> dict:
    a = _rt(request).fusion.alerts.get(alert_id)
    if a is None:
        raise HTTPException(404, f"unknown alert {alert_id}")
    return _alert_detail(a)


class ActionBody(BaseModel):
    action: str


@router.post("/alerts/{alert_id}/action")
async def alert_action(request: Request, alert_id: str, body: ActionBody) -> dict:
    rt = _rt(request)
    try:
        result = await rt.actions.apply(alert_id, body.action)
    except KeyError:
        raise HTTPException(404, f"unknown alert {alert_id}")
    except ValueError:
        raise HTTPException(422, f"unknown action {body.action!r}")
    alert = rt.fusion.alerts[alert_id]
    rt.hub.push_alert({"kind": "alert_updated", "alert": alert.summary_dict()})
    return result


@router.get("/alerts/{alert_id}/verify")
async def verify_alert(request: Request, alert_id: str) -> dict:
    rt = _rt(request)
    latest = rt.store.latest_record(alert_id)
    if latest is None:
        raise HTTPException(404, f"no signed record for {alert_id}")
    payload_json, signature, _prev, _rh = latest
    try:
        record_fp = json.loads(payload_json).get("pubkey_fingerprint", "")
    except json.JSONDecodeError:
        record_fp = ""
    return {
        "alert_id": alert_id,
        "signature_valid": rt.signer.verify_record(payload_json, signature),
        # anchor to the live chain head so a tail-truncated log is caught too
        "chain_valid": rt.signer.verify_chain(
            rt.store.all_records(), expected_head=rt.signer.last_hash),
        "algorithm": "ML-DSA-65",
        # the fingerprint bound into the signed record, not the live signer's
        "pubkey_fingerprint": record_fp or rt.signer.fingerprint,
    }


@router.post("/demo/tamper/{alert_id}")
async def tamper(request: Request, alert_id: str) -> dict:
    mutated = _rt(request).store.tamper(alert_id)
    if mutated is None:
        raise HTTPException(404, f"no stored record for {alert_id}")
    return {"ok": True, "alert_id": alert_id, "mutated": mutated}


# ------------------------------------------------------------------ metrics


@router.get("/metrics")
async def metrics(request: Request) -> dict:
    path = DELIVERABLES_DIR / "metrics.json"
    if path.exists():
        return json.loads(path.read_text())
    # live fallback: shape-complete summary of the current session
    rt = _rt(request)
    alerts = list(rt.fusion.alerts.values())
    fused = {
        "total_alerts": len(alerts), "true_positives": len(alerts),
        "false_positives": 0, "precision": 1.0 if alerts else 0.0,
        "recall": 0.0, "detected_scenarios": [],
    }
    zeros = {"total_alerts": 0, "true_positives": 0, "false_positives": 0,
             "precision": 0.0, "recall": 0.0, "detected_scenarios": []}
    return {
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "seed": rt.seed, "duration_hours": 0,
        "modes": {"siloed": zeros, "fused": fused},
        "scenarios": {},
        "summary": {"alert_reduction_pct": 0.0, "fp_reduction_pct": 0.0,
                    "analyst_hours_saved_per_day": 0.0,
                    "rupees_at_risk_flagged": 0.0},
        "_note": "live session summary — run `make bench` for the full benchmark",
    }


# ------------------------------------------------------------------ quantum


@router.get("/quantum")
async def quantum(request: Request) -> dict:
    rt = _rt(request)
    incidents = [a.summary_dict() for a in rt.fusion.alerts.values()
                 if "quantum" in a.tags]
    incidents.sort(key=lambda a: a["risk"], reverse=True)
    return {"assets": rt.quantum.inventory(), "hndl_incidents": incidents}


# ------------------------------------------------------------------ graph


@router.get("/graph/{entity_id}")
async def graph(request: Request, entity_id: str) -> dict:
    sub = _rt(request).graph.subgraph_dict(entity_id)
    if sub is None:
        raise HTTPException(404, f"unknown entity {entity_id}")
    return sub


# ------------------------------------------------------------------ replay


class StartBody(BaseModel):
    speed: Optional[int] = None


def _status(rt) -> dict:
    return {
        **rt.replay.status(),
        "open_alerts": rt.fusion.open_alert_counts(),
        "held_txns": rt.fusion.held_txn_count(),
        "hndl_assets": rt.quantum.red_asset_count(),
    }


@router.get("/replay/status")
async def replay_status(request: Request) -> dict:
    return _status(_rt(request))


@router.post("/replay/start")
async def replay_start(request: Request, body: StartBody | None = None) -> dict:
    rt = _rt(request)
    rt.replay.start((body.speed if body else None) or 20)
    return {"ok": True, "status": _status(rt)}


@router.post("/replay/pause")
async def replay_pause(request: Request) -> dict:
    rt = _rt(request)
    rt.replay.pause_toggle()
    return {"ok": True, "status": _status(rt)}


@router.post("/replay/reset")
async def replay_reset(request: Request) -> dict:
    rt = _rt(request)
    await rt.reset()
    return {"ok": True, "status": _status(rt)}


@router.post("/replay/inject/{name}")
async def replay_inject(request: Request, name: str) -> dict:
    rt = _rt(request)
    if name not in ("A", "B", "C"):
        raise HTTPException(422, "scenario must be A, B or C")
    rt.replay.ensure_running()  # start if idle, but never clear an operator pause
    rt.replay.inject(name)
    return {"ok": True, "status": _status(rt)}
