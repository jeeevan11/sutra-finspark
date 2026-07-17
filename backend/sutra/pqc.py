"""Post-quantum alert signing: ML-DSA-65 (FIPS 204 / Dilithium) + hash chain.

Every alert create/update is canonical-JSON'd, SHA-256'd and signed. Each signed
record also carries prev_hash = the previous record's hash, forming a tamper-evident
chain across the whole alert log. Keys are generated at first boot and kept under
DATA_DIR/keys (demo scale — an HSM in production).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from dilithium_py.ml_dsa import ML_DSA_65

from .schemas import Alert

GENESIS = "GENESIS"


def canonical_payload(alert: Alert) -> dict:
    # Everything except the signature itself is signed — including the key
    # fingerprint, so a record is bound to the key that produced it and verify
    # can report the RECORD's fingerprint, not whatever key is currently live.
    d = alert.model_dump(mode="json")
    d.pop("signature", None)
    return d


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def digest(payload: dict) -> bytes:
    return hashlib.sha256(canonical_bytes(payload)).digest()


def record_hash(payload_json: str, signature_hex: str) -> str:
    return hashlib.sha256((payload_json + signature_hex).encode()).hexdigest()


class AlertSigner:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is not None:
            keys = data_dir / "keys"
            keys.mkdir(parents=True, exist_ok=True)
            pk_path, sk_path = keys / "mldsa65.pub", keys / "mldsa65.key"
            if pk_path.exists() and sk_path.exists():
                self.pk, self.sk = pk_path.read_bytes(), sk_path.read_bytes()
            else:
                self.pk, self.sk = ML_DSA_65.keygen()
                pk_path.write_bytes(self.pk)
                sk_path.write_bytes(self.sk)
        else:
            self.pk, self.sk = ML_DSA_65.keygen()
        self.fingerprint = hashlib.sha256(self.pk).hexdigest()[:16]
        self.last_hash = GENESIS

    def sign_alert(self, alert: Alert) -> None:
        """Sets prev_hash (chain link), signature, fingerprint on the alert, and
        advances the chain head."""
        alert.prev_hash = self.last_hash
        alert.pubkey_fingerprint = self.fingerprint
        payload = canonical_payload(alert)
        alert.signature = ML_DSA_65.sign(self.sk, digest(payload)).hex()
        self.last_hash = record_hash(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            alert.signature)

    def reset_chain(self) -> None:
        self.last_hash = GENESIS

    # ------------------------------------------------------------------ verify

    def verify_record(self, payload_json: str, signature_hex: str) -> bool:
        try:
            d = hashlib.sha256(payload_json.encode()).digest()
            return ML_DSA_65.verify(self.pk, d, bytes.fromhex(signature_hex))
        except Exception:  # noqa: BLE001 — malformed sig = invalid, never a crash
            return False

    def verify_chain(self, records: list[tuple[str, str, str, str]],
                     expected_head: Optional[str] = None) -> bool:
        """records: (payload_json, signature_hex, prev_hash, record_hash) in
        insertion order. Valid iff, for EVERY record: (a) its ML-DSA signature
        verifies (an unkeyed hash alone could be recomputed by a tamperer —
        including on the chain tail, which linkage cannot see), (b) its stored
        hash matches a fresh recomputation, and (c) its prev_hash equals its
        predecessor's hash (linkage).

        `expected_head` anchors the walk to the live in-memory chain head
        (`self.last_hash`). Without it, a TAIL-TRUNCATED log — delete the last N
        records — is an intact valid prefix and would pass; the anchor catches
        that, since the surviving log's head hash won't match the live head."""
        prev = GENESIS
        for payload_json, signature_hex, prev_hash, stored_hash in records:
            try:
                stored_prev = json.loads(payload_json).get("prev_hash")
            except json.JSONDecodeError:
                return False
            if prev_hash != prev or stored_prev != prev:
                return False
            if record_hash(payload_json, signature_hex) != stored_hash:
                return False
            if not self.verify_record(payload_json, signature_hex):
                return False
            prev = stored_hash
        if expected_head is not None and prev != expected_head:
            return False  # log truncated (or replaced) relative to the live head
        return True
