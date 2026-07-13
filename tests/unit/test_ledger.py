"""Focused tests for the durable local event ledger."""

from __future__ import annotations

import logging
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from threshold.core import ledger as ledger_module
from threshold.core.events import EventBus
from threshold.core.ledger import JsonlLedger, LedgerWitness
from threshold.core.types import EventType, Tier


SYNTHETIC_AGENT = "SYNTHETIC UNIT 04"


def event(sequence: int) -> dict[str, object]:
    return {
        "ts": f"2026-07-12T10:{sequence // 60:02d}:{sequence % 60:02d}+00:00",
        "type": EventType.READ,
        "agent": SYNTHETIC_AGENT,
        "detail": f"synthetic read {sequence}",
    }


def transaction_event(revision: int = 1) -> dict[str, object]:
    return {
        "ts": "2026-07-12T10:00:00Z",
        "type": EventType.GRANT,
        "agent": "g-synthetic-ledger",
        "detail": "synthetic grant issued",
        "transaction": "tx-0123456789abcdef0123456789abcdef",
        "grant_revision": revision,
    }


def test_append_is_durable_private_and_newest_first(tmp_path, monkeypatch):
    path = tmp_path / "private" / "events.jsonl"
    ledger = JsonlLedger(path)
    real_fsync = os.fsync
    fsynced: list[int] = []

    def observed_fsync(descriptor: int) -> None:
        fsynced.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(ledger_module.os, "fsync", observed_fsync)

    ledger.append(event(1))
    ledger.append({**event(2), "tier": Tier.GATED})
    ledger.append(event(3))

    assert fsynced
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [entry["detail"] for entry in ledger.read(limit=2)] == [
        "synthetic read 3",
        "synthetic read 2",
    ]
    assert ledger.read(limit=2)[1]["tier"] == "GATED"


def test_concurrent_instances_append_complete_unmixed_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    ledgers = [JsonlLedger(path) for _ in range(8)]

    def append(sequence: int) -> None:
        ledgers[sequence % len(ledgers)].append(event(sequence))

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append, range(200)))

    entries = ledgers[0].read(limit=500)
    assert len(entries) == 200
    assert {entry["detail"] for entry in entries} == {
        f"synthetic read {sequence}" for sequence in range(200)
    }


def test_prepared_event_has_an_exact_checkpoint_and_verifiable_witness(tmp_path):
    ledger = JsonlLedger(tmp_path / "private" / "events.jsonl")
    prepared = ledger.prepare_event(transaction_event())

    assert ledger.inspect_prepared(prepared) is False
    persisted = ledger.append_prepared(prepared)
    assert persisted == transaction_event()
    assert ledger.inspect_prepared(prepared) is True
    ledger.verify_witness(
        LedgerWitness(
            transaction=str(persisted["transaction"]),
            grant_revision=int(persisted["grant_revision"]),
            ledger_offset=prepared.checkpoint.offset,
            receipt_sha256=prepared.receipt_sha256,
        )
    )
    assert ledger.read()[0]["transaction"] == persisted["transaction"]
    assert ledger.read()[0]["grant_revision"] == 1


def test_prepared_event_refuses_a_changed_tail(tmp_path):
    ledger = JsonlLedger(tmp_path / "private" / "events.jsonl")
    prepared = ledger.prepare_event(transaction_event())
    ledger.append(event(1))

    with pytest.raises(OSError, match="precondition changed"):
        ledger.append_prepared(prepared)
    with pytest.raises(OSError, match="ambiguous"):
        ledger.inspect_prepared(prepared)
    assert [item["type"] for item in ledger.read()] == ["READ"]


def test_read_skips_corrupt_oversized_and_non_object_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    oversized = b"x" * (ledger_module.MAX_ENTRY_BYTES + 1)
    path.write_bytes(
        b'{"ts":"2026-07-12T10:00:00Z","type":"READ","agent":"SYNTHETIC","detail":"one"}\n'
        b"not json\n"
        b"[]\n"
        b"\xff\n"
        + oversized
        + b"\n"
        + b'{"ts":"2026-07-12T10:01:00Z","type":"DENY","agent":"SYNTHETIC","detail":"two"}\n'
    )
    path.chmod(0o600)

    assert [entry["type"] for entry in JsonlLedger(path).read(limit=10)] == [
        "DENY",
        "READ",
    ]


def test_read_is_tolerant_and_does_not_expose_private_paths(tmp_path, caplog):
    missing = JsonlLedger(tmp_path / "missing.jsonl")
    assert missing.read() == []

    invalid_file = tmp_path / "private-ledger-directory"
    invalid_file.mkdir()
    with caplog.at_level(logging.WARNING, logger="threshold.ledger"):
        assert JsonlLedger(invalid_file).read() == []

    assert str(invalid_file) not in caplog.text
    assert "ledger read unavailable" in caplog.text

    with pytest.raises(OSError, match="ledger read unavailable"):
        JsonlLedger(invalid_file).read(fail_on_unavailable=True)


def test_wildcard_handler_allowlists_fields_without_mutating_payload(tmp_path):
    path = tmp_path / "events.jsonl"
    ledger = JsonlLedger(path)
    bus = EventBus()
    ledger.attach(bus)
    payload = {
        "ts": "2026-07-12T10:00:00+00:00",
        "agent": SYNTHETIC_AGENT,
        "detail": "synthetic boundary read",
        "credential": "must-not-be-persisted",
        "raw_adapter_payload": {"synthetic": True},
    }

    bus.emit("READ", payload)

    assert payload["credential"] == "must-not-be-persisted"
    assert ledger.read() == [
        {
            "ts": "2026-07-12T10:00:00+00:00",
            "type": "READ",
            "agent": SYNTHETIC_AGENT,
            "detail": "synthetic boundary read",
        }
    ]


def test_read_drops_unrecognized_fields_from_existing_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"ts":"2026-07-12T10:00:00+00:00","type":"READ",'
        '"agent":"SYNTHETIC","detail":"safe","credential":"not-returned"}\n',
        encoding="utf-8",
    )
    path.chmod(0o600)

    assert JsonlLedger(path).read() == [
        {
            "ts": "2026-07-12T10:00:00+00:00",
            "type": "READ",
            "agent": "SYNTHETIC",
            "detail": "safe",
        }
    ]


def test_read_never_fabricates_missing_or_invalid_persisted_fields(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"type":"READ"}\n'
        '{"ts":"not-a-time","type":"READ","agent":"system","detail":"bad"}\n'
        '{"ts":"2026-07-12T10:00:00Z","type":"READ","detail":"missing agent"}\n'
        '{"ts":"2026-07-12T10:00:00Z","type":"READ","agent":"system"}\n',
        encoding="utf-8",
    )
    path.chmod(0o600)
    assert JsonlLedger(path).read() == []


def test_partial_write_is_rolled_back_before_a_later_success(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    ledger = JsonlLedger(path)
    real_write = os.write
    calls = 0

    def partial_then_fail(descriptor: int, data) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(descriptor, bytes(data[:7]))
        raise OSError("synthetic partial-write failure")

    monkeypatch.setattr(ledger_module.os, "write", partial_then_fail)
    with pytest.raises(OSError):
        ledger.append(event(1))
    monkeypatch.setattr(ledger_module.os, "write", real_write)

    ledger.append(event(2))
    assert [entry["detail"] for entry in ledger.read()] == ["synthetic read 2"]


def test_fsync_failure_rolls_back_event_before_a_later_success(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    ledger = JsonlLedger(path)
    real_fsync = os.fsync
    calls = 0

    def fail_first_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(ledger_module.os, "fsync", fail_first_fsync)
    with pytest.raises(OSError):
        ledger.append(event(1))
    monkeypatch.setattr(ledger_module.os, "fsync", real_fsync)

    ledger.append(event(2))
    assert [entry["detail"] for entry in ledger.read()] == ["synthetic read 2"]


def test_incomplete_tail_is_repaired_before_append(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(
        b'{"ts":"2026-07-12T10:00:00Z","type":"READ",'
        b'"agent":"SYNTHETIC","detail":"complete"}\n'
        b'{"ts":"partial"'
    )
    path.chmod(0o600)
    ledger = JsonlLedger(path)
    ledger.append(event(2))
    assert [entry["detail"] for entry in ledger.read()] == [
        "synthetic read 2",
        "complete",
    ]


def test_oversized_incomplete_tail_fails_closed_without_unbounded_recovery(tmp_path):
    path = tmp_path / "events.jsonl"
    prefix = (
        b'{"ts":"2026-07-12T10:00:00Z","type":"READ",'
        b'"agent":"SYNTHETIC","detail":"complete"}\n'
    )
    original = prefix + b"x" * (ledger_module.MAX_ENTRY_BYTES + 1)
    path.write_bytes(original)
    path.chmod(0o600)

    with pytest.raises(OSError, match="recovery limit"):
        JsonlLedger(path).append(event(2))
    assert path.read_bytes() == original


def test_symlink_ledger_target_is_refused(tmp_path):
    target = tmp_path / "unrelated.json"
    target.write_text("unchanged", encoding="utf-8")
    link = tmp_path / "events.jsonl"
    link.symlink_to(target)

    with pytest.raises(OSError):
        JsonlLedger(link).append(event(1))
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_nonprivate_file_parent_and_symlink_ancestor_are_refused(tmp_path):
    private = tmp_path / "private"
    path = private / "events.jsonl"
    ledger = JsonlLedger(path)
    ledger.append(event(1))
    path.chmod(0o644)

    with pytest.raises(OSError):
        ledger.append(event(2))
    with pytest.raises(OSError, match="ledger read unavailable"):
        ledger.read(fail_on_unavailable=True)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644

    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(OSError):
        JsonlLedger(public / "events.jsonl").append(event(1))

    real = tmp_path / "real-private"
    real.mkdir(mode=0o700)
    real.chmod(0o700)
    linked = tmp_path / "linked-private"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        JsonlLedger(linked / "events.jsonl").append(event(1))
    assert not (real / "events.jsonl").exists()


def test_tail_read_has_a_fixed_byte_budget(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"discarded-prefix\n" * 300_000)
    path.chmod(0o600)
    ledger = JsonlLedger(path)
    ledger.append(event(1))

    real_pread = os.pread
    requested: list[int] = []

    def bounded_pread(descriptor: int, size: int, offset: int) -> bytes:
        requested.append(size)
        return real_pread(descriptor, size, offset)

    monkeypatch.setattr(ledger_module.os, "pread", bounded_pread)
    assert ledger.read(limit=1)[0]["detail"] == "synthetic read 1"
    assert max(requested) <= ledger_module.MAX_READ_BYTES


def test_event_handler_contains_write_failure_without_leaking_path(
    tmp_path,
    caplog,
):
    invalid_file = tmp_path / "private-ledger-directory"
    invalid_file.mkdir()
    bus = EventBus()
    JsonlLedger(invalid_file).attach(bus)

    with caplog.at_level(logging.ERROR, logger="threshold.ledger"):
        bus.emit("DENY", event(1))

    assert "ledger event append failed" in caplog.text
    assert str(invalid_file) not in caplog.text


@pytest.mark.parametrize("limit", [0, -1, True, "10", None])
def test_non_positive_or_invalid_read_limits_are_empty(tmp_path, limit):
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    ledger.append(event(1))
    assert ledger.read(limit=limit) == []


def test_append_rejects_missing_event_type(tmp_path):
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    with pytest.raises(ValueError, match="event type"):
        ledger.append({"agent": SYNTHETIC_AGENT, "detail": "synthetic"})


def test_append_rejects_unknown_event_type(tmp_path):
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    with pytest.raises(ValueError, match="not recognized"):
        ledger.append(
            {
                "type": "UNKNOWN",
                "agent": SYNTHETIC_AGENT,
                "detail": "synthetic",
            }
        )


def test_append_rejects_invalid_supplied_timestamp(tmp_path):
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    with pytest.raises(ValueError, match="timestamp"):
        ledger.append({**event(1), "ts": "not-a-time"})
