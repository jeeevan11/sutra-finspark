"""SQLite persistence: an append-only signed alert log (WAL mode).

Every alert create/update/action appends one signed record; the latest record per
alert_id is its current state. verify walks the full log recomputing hashes.
The demo tamper endpoint mutates a stored record in place — exactly the attack the
signature + chain make evident.
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import (Column, Integer, String, Text, create_engine, event, select)
from sqlalchemy.orm import Session, declarative_base

from .pqc import canonical_payload, record_hash
from .schemas import Alert

Base = declarative_base()


class AlertRecord(Base):
    __tablename__ = "alert_records"
    seq = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(16), index=True, nullable=False)
    ts = Column(String(40), nullable=False)
    payload_json = Column(Text, nullable=False)
    signature = Column(Text, nullable=False, default="")
    prev_hash = Column(String(64), nullable=False, default="")
    record_hash = Column(String(64), nullable=False, default="")


class AlertStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        url = f"sqlite:///{db_path}" if db_path else "sqlite://"
        self.engine = create_engine(url, future=True)
        if db_path:
            @event.listens_for(self.engine, "connect")
            def _pragma(dbapi_conn, _record):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        Base.metadata.create_all(self.engine)

    # ------------------------------------------------------------------ writes

    def append_record(self, alert: Alert) -> None:
        payload = canonical_payload(alert)
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with Session(self.engine) as s:
            s.add(AlertRecord(
                alert_id=alert.alert_id,
                ts=alert.updated_ts.isoformat(),
                payload_json=payload_json,
                signature=alert.signature,
                prev_hash=alert.prev_hash,
                record_hash=record_hash(payload_json, alert.signature),
            ))
            s.commit()

    def tamper(self, alert_id: str) -> Optional[str]:
        """Demo only: mutate the latest stored record's first amount in place,
        bypassing signing. Returns a description of the mutation or None."""
        with Session(self.engine) as s:
            rec = s.execute(
                select(AlertRecord).where(AlertRecord.alert_id == alert_id)
                .order_by(AlertRecord.seq.desc()).limit(1)
            ).scalar_one_or_none()
            if rec is None:
                return None
            payload = json.loads(rec.payload_json)
            mutated = None
            for item in payload.get("evidence", []):
                amt = item.get("detail", {}).get("amount")
                if isinstance(amt, (int, float)) and amt > 0:
                    item["detail"]["amount"] = round(amt / 10, 2)
                    mutated = f"evidence {item['event_id']}: amount ₹{amt:,.0f} → ₹{amt / 10:,.0f}"
                    break
            if mutated is None:
                payload["risk"] = 5
                mutated = "risk → 5"
            rec.payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            s.commit()
            return mutated

    def wipe(self) -> None:
        with Session(self.engine) as s:
            s.query(AlertRecord).delete()
            s.commit()

    # ------------------------------------------------------------------ reads

    def latest_record(self, alert_id: str) -> Optional[tuple[str, str, str, str]]:
        """(payload_json, signature, prev_hash, record_hash) of the newest record."""
        with Session(self.engine) as s:
            rec = s.execute(
                select(AlertRecord).where(AlertRecord.alert_id == alert_id)
                .order_by(AlertRecord.seq.desc()).limit(1)
            ).scalar_one_or_none()
            return (rec.payload_json, rec.signature, rec.prev_hash,
                    rec.record_hash) if rec else None

    def all_records(self) -> list[tuple[str, str, str, str]]:
        with Session(self.engine) as s:
            rows = s.execute(
                select(AlertRecord).order_by(AlertRecord.seq.asc())
            ).scalars().all()
            return [(r.payload_json, r.signature, r.prev_hash, r.record_hash)
                    for r in rows]
