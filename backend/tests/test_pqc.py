"""PQC signing (PS2 outcome 4 infrastructure): sign→verify, tamper→fail, chain."""

from datetime import datetime, timezone

from sutra.pqc import AlertSigner
from sutra.schemas import Alert, EvidenceItem
from sutra.store import AlertStore

NOW = datetime(2026, 2, 14, 15, 0, 0, tzinfo=timezone.utc)


def _alert(i: int, amount: float = 49_900.0) -> Alert:
    return Alert(
        alert_id=f"ALT-{i:04d}", created_ts=NOW, updated_ts=NOW,
        entity_type="customer", entity_id="CUST-0421", risk=97,
        severity="critical", title="test", narrative="n",
        evidence=[EvidenceItem(event_id=f"EVT-{i}", ts=NOW, type="txn",
                               summary="s", detail={"amount": amount})],
    )


def test_sign_and_verify_roundtrip():
    signer = AlertSigner()
    store = AlertStore()
    a = _alert(1)
    signer.sign_alert(a)
    store.append_record(a)
    payload_json, sig, _, _ = store.latest_record(a.alert_id)
    assert signer.verify_record(payload_json, sig)
    assert a.pubkey_fingerprint == signer.fingerprint
    assert a.prev_hash == "GENESIS"


def test_tamper_breaks_signature_and_chain():
    signer = AlertSigner()
    store = AlertStore()
    for i in (1, 2):
        a = _alert(i)
        signer.sign_alert(a)
        store.append_record(a)
    assert AlertSigner.verify_chain(store.all_records())
    mutated = store.tamper("ALT-0002")
    assert mutated and "amount" in mutated
    payload_json, sig, _, _ = store.latest_record("ALT-0002")
    assert not signer.verify_record(payload_json, sig)
    assert not AlertSigner.verify_chain(store.all_records())
    # the untampered record still verifies
    p1, s1, _, _ = store.latest_record("ALT-0001")
    assert signer.verify_record(p1, s1)


def test_chain_links_updates_of_same_alert():
    signer = AlertSigner()
    store = AlertStore()
    a = _alert(1)
    signer.sign_alert(a)
    store.append_record(a)
    a.risk = 100
    a.severity = "critical"
    signer.sign_alert(a)  # update re-signs with prev_hash of the first record
    store.append_record(a)
    records = store.all_records()
    assert len(records) == 2
    assert AlertSigner.verify_chain(records)
    assert a.prev_hash != "GENESIS"


def test_wrong_key_rejects():
    signer_a, signer_b = AlertSigner(), AlertSigner()
    a = _alert(1)
    signer_a.sign_alert(a)
    store = AlertStore()
    store.append_record(a)
    payload_json, sig, _, _ = store.latest_record(a.alert_id)
    assert not signer_b.verify_record(payload_json, sig)
