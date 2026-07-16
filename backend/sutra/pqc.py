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
    d = alert.model_dump(mode="json")
    d.pop("signature", None)
    d.pop("pubkey_fingerprint", None)
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

    @staticmethod
    def verify_chain(records: list[tuple[str, str, str, str]]) -> bool:
        """records: (payload_json, signature_hex, prev_hash, record_hash) in
        insertion order. Valid iff (a) every record's stored hash matches a fresh
        recomputation of its content (self-integrity — this is what catches a
        mutated chain TAIL, which linkage alone cannot see) and (b) every
        prev_hash equals its predecessor's hash (linkage)."""
        prev = GENESIS
        for payload_json, signature_hex, prev_hash, stored_hash in records:
            try:
                stored_prev = json.loads(payload_json).get("prev_hash")
            except json.JSONDecodeError:
                return False
            if prev_hash != prev or stored_prev != prev:
                return False
            recomputed = record_hash(payload_json, signature_hex)
            if recomputed != stored_hash:
                return False
            prev = recomputed
        return True
