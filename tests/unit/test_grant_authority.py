"""Adversarial recovery proofs for the authoritative grant coordinator."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from threshold.capture.seed import SEED_FILE
from threshold.core.auth import token_digest
from threshold.core.ledger import JsonlLedger
from threshold.core.types import EventType, Grant, GrantStatus, Scope
from threshold.grants.authority import (
    GrantAuthority,
    GrantAuthorityUnavailable,
    GrantCredentialConflict,
)
from threshold.grants.store import GrantMetadataStore


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
SYNTHETIC_CREDENTIAL = "synthetic-authority-credential-000000000001"


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def grant(identifier: str = "g-authority-test", **changes: object) -> Grant:
    values: dict[str, object] = {
        "id": identifier,
        "name": "Synthetic Authority Agent",
        "kind": "agent",
        "scopes": (Scope.READ_LAYOUT, Scope.CMD_NAVIGATE),
        "zones": ("kitchen",),
        "window": "standing",
        "expires": "revocable",
        "status": GrantStatus.ACTIVE,
        "issued": timestamp(NOW),
        "credential_digest": token_digest(SYNTHETIC_CREDENTIAL + identifier),
    }
    values.update(changes)
    return Grant(**values)  # type: ignore[arg-type]


def paths(tmp_path):
    private = tmp_path / "private"
    return private / "grants.json", private / "ledger.jsonl"


def authority(tmp_path, *, demo_seed: Grant | None = None) -> GrantAuthority:
    store_path, ledger_path = paths(tmp_path)
    return GrantAuthority(
        SEED_FILE,
        GrantMetadataStore(store_path),
        JsonlLedger(ledger_path),
        demo_mode=demo_seed is not None,
        demo_seeds=(() if demo_seed is None else (demo_seed,)),
    )


def test_issue_restart_is_witnessed_digest_only_and_deterministic(tmp_path):
    first = authority(tmp_path)
    issued = first.issue(grant(), now=NOW)

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    store_path, ledger_path = paths(tmp_path)

    assert restarted.revision == 1
    assert restarted.grants[issued.id].credential_digest == token_digest(
        SYNTHETIC_CREDENTIAL + issued.id
    )
    assert SYNTHETIC_CREDENTIAL.encode() not in store_path.read_bytes()
    assert SYNTHETIC_CREDENTIAL.encode() not in ledger_path.read_bytes()
    assert "credential_digest" not in ledger_path.read_text(encoding="utf-8")
    assert [event["type"] for event in restarted.ledger.read()] == ["GRANT"]


@pytest.mark.parametrize(
    ("transition", "expected"),
    [
        ("revoke", GrantStatus.REVOKED),
        ("expire", GrantStatus.EXPIRED),
        ("suspend", GrantStatus.SUSPENDED),
    ],
)
def test_restrictive_states_persist_across_restart(tmp_path, transition, expected):
    current = authority(tmp_path)
    item = grant(expires=timestamp(NOW + timedelta(minutes=1)))
    current.issue(item, now=NOW)

    if transition == "revoke":
        current.revoke(item.id, now=NOW)
    elif transition == "expire":
        _, decision = current.decision(
            item.id,
            now=NOW + timedelta(minutes=1),
            action="scoped read",
        )
        assert decision.reason == "grant_expired"
    else:
        assert current.suspend_all(now=NOW) == 1

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.grants[item.id].status == expected


@pytest.mark.parametrize(
    "time_policy",
    [
        {"expires": timestamp(NOW)},
        {
            "window": (
                f"{timestamp(NOW - timedelta(minutes=30))}/{timestamp(NOW)}"
            )
        },
    ],
    ids=("expiry", "window-end"),
)
def test_snapshot_persists_first_observed_expiry_across_restart(
    tmp_path,
    time_policy,
):
    current = authority(tmp_path)
    item = grant(
        "g-owner-observed-expiry",
        issued=timestamp(NOW - timedelta(hours=1)),
        **time_policy,
    )
    current.issue(item, now=NOW - timedelta(hours=1))

    projected = current.snapshot(now=NOW)

    assert projected[item.id].status == GrantStatus.EXPIRED
    assert current.grants[item.id].status == GrantStatus.EXPIRED
    event = current.ledger.read()[0]
    assert event["ts"] == timestamp(NOW)
    assert event["type"] == EventType.DENY.value
    assert event["agent"] == item.id
    assert event["detail"] == "owner projection observed: grant_expired"
    assert event["grant_revision"] == 2
    assert isinstance(event["transaction"], str)

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.grants[item.id].status == GrantStatus.EXPIRED


def test_pending_issue_without_receipt_never_becomes_effective(tmp_path, monkeypatch):
    current = authority(tmp_path)

    def fail_append(_prepared):
        raise OSError("synthetic append boundary failure")

    monkeypatch.setattr(current.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        current.issue(grant(), now=NOW)

    store_path, _ = paths(tmp_path)
    raw = store_path.read_bytes()
    assert SYNTHETIC_CREDENTIAL.encode() not in raw
    assert GrantMetadataStore(store_path).load() == {}

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.grants == {}
    assert restarted.revision == 0


def test_pending_revoke_stays_denied_and_rolls_forward(tmp_path, monkeypatch):
    current = authority(tmp_path)
    item = current.issue(grant(), now=NOW)

    def fail_append(_prepared):
        raise OSError("synthetic append boundary failure")

    monkeypatch.setattr(current.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        current.revoke(item.id, now=NOW)

    store_path, _ = paths(tmp_path)
    assert GrantMetadataStore(store_path).load()[item.id].status == GrantStatus.REVOKED

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.grants[item.id].status == GrantStatus.REVOKED
    assert [event["type"] for event in restarted.ledger.read()].count("REVOKE") == 1


def test_pending_suspend_all_cannot_hide_an_active_grant(tmp_path, monkeypatch):
    current = authority(tmp_path)
    item = current.issue(grant(), now=NOW)

    def fail_append(_prepared):
        raise OSError("synthetic append boundary failure")

    monkeypatch.setattr(current.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        current.suspend_all(now=NOW)

    store_path, _ = paths(tmp_path)
    document = json.loads(store_path.read_text(encoding="utf-8"))
    document["grants"][0]["status"] = GrantStatus.ACTIVE.value
    document["pending"]["target_grants"][0]["status"] = GrantStatus.ACTIVE.value
    document["pending"]["previous_statuses"] = {}
    document["pending"]["target_sha256"] = GrantMetadataStore.target_sha256(
        {item.id: item}
    )
    store_path.write_text(
        json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    store_path.chmod(0o600)

    with pytest.raises(GrantAuthorityUnavailable):
        authority(tmp_path).ensure_ready(now=NOW)


def test_pending_revoke_cannot_inject_an_unrelated_active_grant(
    tmp_path,
    monkeypatch,
):
    current = authority(tmp_path)
    item = current.issue(grant(), now=NOW)

    def fail_append(_prepared):
        raise OSError("synthetic append boundary failure")

    monkeypatch.setattr(current.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        current.revoke(item.id, now=NOW)

    injected = grant("g-injected-active")
    revoked = grant(status=GrantStatus.REVOKED)
    injected_record = GrantMetadataStore._normalize_outgoing([injected])[0]
    store_path, _ = paths(tmp_path)
    document = json.loads(store_path.read_text(encoding="utf-8"))
    document["grants"].append(injected_record)
    document["pending"]["target_grants"].append(injected_record)
    document["grants"].sort(key=lambda record: record["id"])
    document["pending"]["target_grants"].sort(
        key=lambda record: record["id"]
    )
    document["pending"]["target_sha256"] = GrantMetadataStore.target_sha256(
        {revoked.id: revoked, injected.id: injected}
    )
    store_path.write_text(
        json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    store_path.chmod(0o600)

    with pytest.raises(GrantAuthorityUnavailable):
        authority(tmp_path).ensure_ready(now=NOW)


def test_pending_recovery_verifies_the_prior_ledger_receipt(tmp_path, monkeypatch):
    current = authority(tmp_path)
    item = current.issue(grant(), now=NOW)

    def fail_append(_prepared):
        raise OSError("synthetic append boundary failure")

    monkeypatch.setattr(current.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        current.revoke(item.id, now=NOW)

    _, ledger_path = paths(tmp_path)
    with ledger_path.open("r+b") as handle:
        handle.truncate(0)
        handle.flush()
        os.fsync(handle.fileno())

    restarted = authority(tmp_path)
    with pytest.raises(GrantAuthorityUnavailable):
        restarted.ensure_ready(now=NOW)
    assert restarted.ledger.read() == []


def test_exact_receipt_recovers_after_final_store_failure(tmp_path, monkeypatch):
    current = authority(tmp_path)
    store = current.store
    real_save = store.save_state
    saves = 0

    def fail_final(state):
        nonlocal saves
        saves += 1
        if saves == 2:
            raise OSError("synthetic final snapshot failure")
        real_save(state)

    monkeypatch.setattr(store, "save_state", fail_final)
    with pytest.raises(GrantAuthorityUnavailable):
        current.issue(grant(), now=NOW)

    store_path, _ = paths(tmp_path)
    assert GrantMetadataStore(store_path).load() == {}

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.grants["g-authority-test"].status == GrantStatus.ACTIVE
    assert restarted.revision == 1


def test_pending_offset_mismatch_is_ambiguous_and_fails_closed(tmp_path, monkeypatch):
    current = authority(tmp_path)

    def fail_append(_prepared):
        raise OSError("synthetic append boundary failure")

    monkeypatch.setattr(current.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        current.issue(grant(), now=NOW)

    store_path, _ = paths(tmp_path)
    document = json.loads(store_path.read_text(encoding="utf-8"))
    document["pending"]["ledger_offset"] += 1
    store_path.write_text(
        json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    store_path.chmod(0o600)

    with pytest.raises(GrantAuthorityUnavailable):
        authority(tmp_path).ensure_ready(now=NOW)


def test_corrupt_existing_store_never_falls_back_to_demo_seed(tmp_path):
    store_path, _ = paths(tmp_path)
    store_path.parent.mkdir(mode=0o700)
    store_path.parent.chmod(0o700)
    store_path.write_bytes(b"not-json")
    store_path.chmod(0o600)

    with pytest.raises(GrantAuthorityUnavailable):
        authority(tmp_path, demo_seed=grant("g-demo-seed")).ensure_ready(now=NOW)
    assert store_path.read_bytes() == b"not-json"


def test_missing_store_with_existing_ledger_history_is_ambiguous(tmp_path):
    _, ledger_path = paths(tmp_path)
    JsonlLedger(ledger_path).append(
        {
            "ts": timestamp(NOW),
            "type": EventType.READ.value,
            "agent": "g-synthetic-history",
            "detail": "synthetic prior history",
        }
    )
    with pytest.raises(GrantAuthorityUnavailable):
        authority(tmp_path).ensure_ready(now=NOW)


def test_demo_seed_is_first_boot_only_and_recovers_missing_receipt(tmp_path, monkeypatch):
    demo = grant("g-demo-seed")
    first = authority(tmp_path, demo_seed=demo)

    def fail_append(_prepared):
        raise OSError("synthetic append boundary failure")

    monkeypatch.setattr(first.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        first.ensure_ready(now=NOW)
    assert GrantMetadataStore(paths(tmp_path)[0]).load() == {}

    restarted = authority(tmp_path, demo_seed=demo)
    restarted.ensure_ready(now=NOW)
    assert set(restarted.grants) == {"g-demo-seed"}
    assert [event["type"] for event in restarted.ledger.read()].count("PROVISION") == 1

    changed_seed = grant("g-different-demo-seed")
    later = authority(tmp_path, demo_seed=changed_seed)
    later.ensure_ready(now=NOW)
    assert set(later.grants) == {"g-demo-seed"}


def test_ledger_truncation_invalidates_clean_store_witness(tmp_path):
    current = authority(tmp_path)
    current.issue(grant(), now=NOW)
    _, ledger_path = paths(tmp_path)
    with ledger_path.open("r+b") as handle:
        handle.truncate(0)
        handle.flush()
        os.fsync(handle.fileno())

    with pytest.raises(GrantAuthorityUnavailable):
        authority(tmp_path).ensure_ready(now=NOW)


def test_clean_snapshot_edit_invalidates_committed_target_witness(tmp_path):
    current = authority(tmp_path)
    item = current.issue(grant(), now=NOW)
    current.revoke(item.id, now=NOW)

    store_path, _ = paths(tmp_path)
    document = json.loads(store_path.read_text(encoding="utf-8"))
    document["grants"][0]["status"] = GrantStatus.ACTIVE.value
    store_path.write_text(
        json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    store_path.chmod(0o600)

    with pytest.raises(GrantAuthorityUnavailable):
        authority(tmp_path).ensure_ready(now=NOW)


def test_stale_authority_reloads_before_committing(tmp_path):
    first = authority(tmp_path)
    stale = authority(tmp_path)
    first.ensure_ready(now=NOW)
    stale.ensure_ready(now=NOW)

    first.issue(grant("g-first-authority"), now=NOW)
    stale.issue(grant("g-stale-authority"), now=NOW)

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.revision == 2
    assert set(restarted.grants) == {"g-first-authority", "g-stale-authority"}
    assert [event["type"] for event in restarted.ledger.read()].count("GRANT") == 2


def test_stale_authority_cannot_reuse_a_committed_credential(tmp_path):
    first = authority(tmp_path)
    stale = authority(tmp_path)
    first.ensure_ready(now=NOW)
    stale.ensure_ready(now=NOW)
    issued = first.issue(grant("g-first-credential"), now=NOW)

    with pytest.raises(GrantCredentialConflict):
        stale.issue(
            grant(
                "g-duplicate-credential",
                credential_digest=issued.credential_digest,
            ),
            now=NOW,
        )

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.revision == 1
    assert set(restarted.grants) == {issued.id}


def test_concurrent_authorities_serialize_complete_transactions(tmp_path):
    authorities = (authority(tmp_path), authority(tmp_path))
    for current in authorities:
        current.ensure_ready(now=NOW)
    barrier = threading.Barrier(3)

    def issue(current: GrantAuthority, identifier: str) -> str:
        barrier.wait()
        return current.issue(grant(identifier), now=NOW).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(issue, authorities[0], "g-concurrent-one"),
            pool.submit(issue, authorities[1], "g-concurrent-two"),
        ]
        barrier.wait()
        assert {future.result(timeout=5) for future in futures} == {
            "g-concurrent-one",
            "g-concurrent-two",
        }

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.revision == 2
    assert set(restarted.grants) == {"g-concurrent-one", "g-concurrent-two"}
    assert [event["type"] for event in restarted.ledger.read()].count("GRANT") == 2


def test_authorization_lease_blocks_revoke_until_protected_use_finishes(tmp_path):
    reader = authority(tmp_path)
    revoker = authority(tmp_path)
    item = reader.issue(grant("g-leased-authority"), now=NOW)
    credential = SYNTHETIC_CREDENTIAL + item.id
    lease_entered = threading.Event()
    release_lease = threading.Event()
    revoke_started = threading.Event()
    revoke_finished = threading.Event()

    def protected_read() -> None:
        with reader.authorized(
            item.id,
            credential,
            now=NOW,
            action="scoped read",
        ) as (leased, decision):
            assert decision.allowed is True
            assert leased.status == GrantStatus.ACTIVE
            lease_entered.set()
            assert release_lease.wait(timeout=5)

    def revoke() -> None:
        assert lease_entered.wait(timeout=5)
        revoke_started.set()
        revoker.revoke(item.id, now=NOW)
        revoke_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        read_future = pool.submit(protected_read)
        revoke_future = pool.submit(revoke)
        assert revoke_started.wait(timeout=5)
        assert revoke_finished.wait(timeout=0.1) is False
        release_lease.set()
        read_future.result(timeout=5)
        revoke_future.result(timeout=5)

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.grants[item.id].status == GrantStatus.REVOKED


def test_zero_active_trip_still_has_one_durable_estop_receipt(tmp_path):
    current = authority(tmp_path)

    assert current.suspend_all(now=NOW) == 0

    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.revision == 1
    assert restarted.grants == {}
    assert [event["type"] for event in restarted.ledger.read()] == ["ESTOP"]


def test_pending_zero_active_trip_recovers_one_estop_receipt(tmp_path, monkeypatch):
    current = authority(tmp_path)

    def fail_append(_prepared):
        raise OSError("synthetic zero-grant append failure")

    monkeypatch.setattr(current.ledger, "append_prepared", fail_append)
    with pytest.raises(GrantAuthorityUnavailable):
        current.suspend_all(now=NOW)

    assert GrantMetadataStore(paths(tmp_path)[0]).load() == {}
    restarted = authority(tmp_path)
    restarted.ensure_ready(now=NOW)
    assert restarted.revision == 1
    assert restarted.grants == {}
    assert [event["type"] for event in restarted.ledger.read()] == ["ESTOP"]
