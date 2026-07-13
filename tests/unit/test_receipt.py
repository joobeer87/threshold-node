"""Focused deterministic and privacy tests for THS-0043 receipts."""

from __future__ import annotations

import binascii
import hashlib
import inspect
import os
import stat
import struct
import zlib
from datetime import datetime, timedelta, timezone

import pytest

from threshold.hardware import receipt as receipt_module
from threshold.hardware.receipt import (
    PNG_HEIGHT,
    PNG_SIGNATURE,
    PNG_WIDTH,
    ReceiptStorageError,
    ReceiptValidationError,
    SyntheticReceipt,
    build_receipt,
    render_receipt_png,
    write_receipt_png,
)


SYNTHETIC_INSTANT = datetime(2026, 7, 18, 14, 2, 3, tzinfo=timezone.utc)


def grant_receipt():
    return build_receipt(
        "GRANT",
        occurred_at=SYNTHETIC_INSTANT,
        sequence=41,
        actor="Synthetic Unit 04",
        scopes=("read:layout", "read:inventory", "command:navigate"),
        zones=("kitchen", "living", "office"),
        tier="GATED",
    )


def parse_png(data: bytes) -> list[tuple[bytes, bytes]]:
    assert data.startswith(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(data):
        assert offset + 12 <= len(data)
        length = struct.unpack("!I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        assert end + 4 <= len(data)
        payload = data[start:end]
        observed_crc = struct.unpack("!I", data[end : end + 4])[0]
        expected_crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        assert observed_crc == expected_crc
        chunks.append((chunk_type, payload))
        offset = end + 4
        if chunk_type == b"IEND":
            break
    assert offset == len(data)
    return chunks


def test_allowlisted_templates_are_canonical_bounded_and_visibly_simulated():
    grant = grant_receipt()
    deny = build_receipt(
        "DENY",
        occurred_at=datetime(
            2026,
            7,
            18,
            10,
            2,
            3,
            tzinfo=timezone(timedelta(hours=-4)),
        ),
        sequence=42,
        actor="Synthetic Unit 04",
        zones=("workshop",),
        reason="no-go",
    )
    estop = build_receipt(
        "ESTOP",
        occurred_at=SYNTHETIC_INSTANT,
        sequence=43,
        actor="Synthetic Interlock",
    )

    assert grant.text == (
        "THRESHOLD / SYNTHETIC DEMO\n"
        "2026-07-18 14:02:03Z #000041\n"
        "GRANT: SYNTHETIC UNIT 04\n"
        "SCOPES: INVENTORY,LAYOUT,NAV\n"
        "ZONES: KITCHEN,LIVING,OFFICE\n"
        "TIER: GATED\n"
        "SIMULATED SOFTWARE PATH\n"
        "NOT A SAFETY SYSTEM\n"
    )
    assert deny.lines == (
        "THRESHOLD / SYNTHETIC DEMO",
        "2026-07-18 14:02:03Z #000042",
        "DENY: SYNTHETIC UNIT 04",
        "ZONE: WORKSHOP",
        "REASON: NO-GO",
        "SIMULATED SOFTWARE PATH",
        "NOT A SAFETY SYSTEM",
    )
    assert estop.lines == (
        "THRESHOLD / SYNTHETIC DEMO",
        "2026-07-18 14:02:03Z #000043",
        "ESTOP: SYNTHETIC INTERLOCK",
        "STATE: TRIPPED",
        "GRANTS: SUSPENDED",
        "SIMULATED SOFTWARE PATH",
        "NOT A SAFETY SYSTEM",
    )
    assert all(len(line) <= 30 for item in (grant, deny, estop) for line in item.lines)


def test_builder_signature_excludes_secrets_digests_and_arbitrary_payloads():
    fields = set(inspect.signature(build_receipt).parameters)
    assert fields == {
        "event_type",
        "occurred_at",
        "sequence",
        "actor",
        "scopes",
        "zones",
        "tier",
        "reason",
    }
    for forbidden in ("credential", "digest", "raw_payload", "payload", "detail"):
        assert forbidden not in fields

    with pytest.raises(TypeError):
        build_receipt(  # type: ignore[call-arg]
            "ESTOP",
            occurred_at=SYNTHETIC_INSTANT,
            sequence=1,
            actor="Synthetic Interlock",
            credential="synthetic-private-value",
        )
    with pytest.raises(ReceiptValidationError):
        build_receipt(
            "ESTOP",
            occurred_at=SYNTHETIC_INSTANT,
            sequence=1,
            actor="Synthetic Credential",
        )


def test_direct_or_mutated_receipt_lines_cannot_render_or_persist(tmp_path):
    arbitrary_lines = (
        "THRESHOLD / SYNTHETIC DEMO",
        "PRIVATE ROOM NOTE",
    )
    with pytest.raises(ReceiptValidationError, match="construction is invalid"):
        SyntheticReceipt("ESTOP", arbitrary_lines)

    receipt = build_receipt(
        "ESTOP",
        occurred_at=SYNTHETIC_INSTANT,
        sequence=1,
        actor="Synthetic Interlock",
    )
    object.__setattr__(receipt, "lines", arbitrary_lines)
    with pytest.raises(ReceiptValidationError, match="integrity is invalid"):
        _ = receipt.text
    with pytest.raises(ReceiptValidationError, match="integrity is invalid"):
        receipt.text_bytes()
    with pytest.raises(ReceiptValidationError, match="integrity is invalid"):
        render_receipt_png(receipt)

    target = tmp_path / "private-receipts" / "receipt.png"
    with pytest.raises(ReceiptValidationError, match="integrity is invalid"):
        write_receipt_png(receipt, target)
    assert not target.exists()


@pytest.mark.parametrize(
    "event_type",
    ["READ", "REVOKE", "PROVISION", "grant", "", []],
)
def test_non_receipt_event_types_are_rejected(event_type):
    with pytest.raises(ReceiptValidationError):
        build_receipt(
            event_type,
            occurred_at=SYNTHETIC_INSTANT,
            sequence=1,
            actor="Synthetic Unit 04",
        )


def test_timestamp_sequence_and_display_labels_fail_closed():
    for invalid_timestamp in (
        datetime(2026, 7, 18, 14, 2, 3),
        "2026-07-18T14:02:03Z",
    ):
        with pytest.raises(ReceiptValidationError):
            build_receipt(
                "ESTOP",
                occurred_at=invalid_timestamp,  # type: ignore[arg-type]
                sequence=1,
                actor="Synthetic Interlock",
            )
    for invalid_sequence in (True, 0, 1_000_000, "1"):
        with pytest.raises(ReceiptValidationError):
            build_receipt(
                "ESTOP",
                occurred_at=SYNTHETIC_INSTANT,
                sequence=invalid_sequence,  # type: ignore[arg-type]
                actor="Synthetic Interlock",
            )
    for invalid_actor in (
        "",
        "Synthetic\nInterlock",
        "Synthetic Interlock With A Label That Is Too Long",
        "Synthetic 🔑",
    ):
        with pytest.raises(ReceiptValidationError):
            build_receipt(
                "ESTOP",
                occurred_at=SYNTHETIC_INSTANT,
                sequence=1,
                actor=invalid_actor,
            )


def test_kind_specific_fields_and_value_allowlists_fail_closed():
    common = {
        "occurred_at": SYNTHETIC_INSTANT,
        "sequence": 1,
        "actor": "Synthetic Unit 04",
    }
    invalid_calls = (
        ("GRANT", {"zones": ("kitchen",), "tier": "GATED"}),
        (
            "GRANT",
            {
                "scopes": ("read:unknown",),
                "zones": ("kitchen",),
                "tier": "GATED",
            },
        ),
        (
            "GRANT",
            {
                "scopes": ("read:layout", "read:layout"),
                "zones": ("kitchen",),
                "tier": "GATED",
            },
        ),
        (
            "GRANT",
            {
                "scopes": ("read:layout",),
                "zones": ("kitchen", "KITCHEN"),
                "tier": "GATED",
            },
        ),
        (
            "GRANT",
            {
                "scopes": ("read:layout",),
                "zones": ("kitchen",),
                "tier": "CERTIFIED",
            },
        ),
        ("DENY", {"zones": ("one", "two"), "reason": "no-go"}),
        ("DENY", {"reason": "private free-form reason"}),
        ("DENY", {"reason": []}),
        ("DENY", {"reason": "no-go", "tier": "GATED"}),
        ("DENY", {"reason": "no-go", "tier": []}),
        ("ESTOP", {"zones": ("kitchen",)}),
        ("ESTOP", {"scopes": ([],)}),
    )
    for event_type, changes in invalid_calls:
        with pytest.raises(ReceiptValidationError):
            build_receipt(event_type, **common, **changes)


def test_png_is_stable_minimal_valid_and_uses_fixed_bitmap():
    receipt = grant_receipt()
    first = render_receipt_png(receipt)
    second = render_receipt_png(grant_receipt())

    assert first == second
    assert hashlib.sha256(first).hexdigest() == (
        "a36f0ed30a6069b8051ef91f2e81c21ca11787f9f44d1f7fcdd0094bbc29227c"
    )
    chunks = parse_png(first)
    assert [chunk_type for chunk_type, _ in chunks] == [b"IHDR", b"IDAT", b"IEND"]
    assert chunks[0][1] == struct.pack("!IIBBBBB", PNG_WIDTH, PNG_HEIGHT, 8, 0, 0, 0, 0)

    raw = zlib.decompress(chunks[1][1])
    stride = PNG_WIDTH + 1
    assert len(raw) == stride * PNG_HEIGHT
    assert all(raw[row * stride] == 0 for row in range(PNG_HEIGHT))
    assert raw[0 * stride + 1] == 255
    assert raw[12 * stride + 1 + 12] == 0  # Top-left pixel of the fixed T glyph.
    assert raw.count(0) > PNG_HEIGHT  # Filter bytes plus rendered black pixels.


def test_distinct_allowlisted_receipts_produce_distinct_pngs():
    estop = build_receipt(
        "ESTOP",
        occurred_at=SYNTHETIC_INSTANT,
        sequence=43,
        actor="Synthetic Interlock",
    )
    assert render_receipt_png(estop) != render_receipt_png(grant_receipt())


def test_private_png_sink_is_write_once_and_enforces_modes(tmp_path):
    path = tmp_path / "private-receipts" / "receipt-000041.png"
    persisted = write_receipt_png(grant_receipt(), path)
    original = path.read_bytes()

    assert persisted == path.absolute()
    assert original == render_receipt_png(grant_receipt())
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
    with pytest.raises(ReceiptStorageError):
        write_receipt_png(grant_receipt(), path)
    assert path.read_bytes() == original


def test_sink_rejects_symlinks_hardlinks_and_nonprivate_directories(tmp_path):
    real_private = tmp_path / "real-private"
    real_private.mkdir(mode=0o700)
    real_private.chmod(0o700)
    source = real_private / "source.png"
    source.write_bytes(b"synthetic-existing-file")
    source.chmod(0o600)

    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_private, target_is_directory=True)
    with pytest.raises(ReceiptStorageError):
        write_receipt_png(grant_receipt(), linked_parent / "receipt.png")

    linked_file = real_private / "linked.png"
    linked_file.symlink_to(source)
    with pytest.raises(ReceiptStorageError):
        write_receipt_png(grant_receipt(), linked_file)

    hardlinked_file = real_private / "hardlinked.png"
    os.link(source, hardlinked_file)
    with pytest.raises(ReceiptStorageError):
        write_receipt_png(grant_receipt(), hardlinked_file)
    assert source.read_bytes() == b"synthetic-existing-file"

    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(ReceiptStorageError):
        write_receipt_png(grant_receipt(), public / "receipt.png")


def test_sink_failure_removes_partial_file(tmp_path, monkeypatch):
    path = tmp_path / "private-receipts" / "receipt.png"
    real_fsync = os.fsync

    def fail_file_fsync(descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("synthetic file fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(receipt_module.os, "fsync", fail_file_fsync)
    with pytest.raises(ReceiptStorageError, match="receipt sink unavailable"):
        write_receipt_png(grant_receipt(), path)
    assert not path.exists()


@pytest.mark.parametrize(
    "name",
    ["receipt.txt", ".receipt.png", "receipt name.png", "receipt?.png"],
)
def test_sink_rejects_invalid_leaf_names(tmp_path, name):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    with pytest.raises(ReceiptStorageError, match="receipt sink path is invalid"):
        write_receipt_png(grant_receipt(), private / name)
