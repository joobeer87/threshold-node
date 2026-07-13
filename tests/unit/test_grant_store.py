"""Focused security and durability tests for THS-0017 grant metadata."""

from __future__ import annotations

import json
import os
import stat

import pytest

from threshold.core.auth import token_digest
from threshold.core.types import Grant, GrantStatus, Scope
from threshold.grants import store as store_module
from threshold.grants.store import GrantMetadataStore, GrantStoreError


SYNTHETIC_CREDENTIAL = "synthetic-grant-credential-000000000001"


def grant(identifier: str = "g-synthetic-one", **changes: object) -> Grant:
    values: dict[str, object] = {
        "id": identifier,
        "name": "Synthetic Test Agent",
        "kind": "agent",
        "scopes": (Scope.READ_LAYOUT, Scope.CMD_NAVIGATE),
        "zones": ("kitchen",),
        "window": "standing",
        "expires": "revocable",
        "status": GrantStatus.ACTIVE,
        "issued": "2026-07-13T01:00:00Z",
        "credential_digest": token_digest(SYNTHETIC_CREDENTIAL + identifier),
    }
    values.update(changes)
    return Grant(**values)  # type: ignore[arg-type]


def private_path(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory / "grants.json"


def write_private(path, data: bytes) -> None:
    path.write_bytes(data)
    path.chmod(0o600)


def test_restart_round_trip_is_deterministic_private_and_digest_only(tmp_path):
    path = private_path(tmp_path)
    store = GrantMetadataStore(path)
    second = grant("g-synthetic-two", name="Synthetic Second Agent")

    store.save({second.id: second, "g-synthetic-one": grant()})
    first_bytes = path.read_bytes()
    restarted = GrantMetadataStore(path).load()
    GrantMetadataStore(path).save(restarted)

    assert path.read_bytes() == first_bytes
    assert list(restarted) == ["g-synthetic-one", "g-synthetic-two"]
    assert restarted["g-synthetic-one"].credential_digest == token_digest(
        SYNTHETIC_CREDENTIAL + "g-synthetic-one"
    )
    assert SYNTHETIC_CREDENTIAL.encode() not in first_bytes
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_missing_store_is_empty_and_save_creates_private_leaf(tmp_path):
    path = tmp_path / "private" / "grants.json"
    store = GrantMetadataStore(path)
    assert store.load() == {}
    store.save([grant()])
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.update(extra=True),
        lambda document: document.update(schema="ths/grant-metadata/9.9"),
        lambda document: document["grants"][0].update(
            credential_digest=SYNTHETIC_CREDENTIAL
        ),
        lambda document: document["grants"][0].update(scopes=["read:layout", "read:layout"]),
        lambda document: document["grants"][0].update(status="unknown"),
        lambda document: document["grants"].append(dict(document["grants"][0])),
    ],
)
def test_corrupt_or_noncanonical_document_fails_as_one_unit(tmp_path, mutation):
    path = private_path(tmp_path)
    GrantMetadataStore(path).save([grant()])
    document = json.loads(path.read_text(encoding="utf-8"))
    mutation(document)
    write_private(path, json.dumps(document).encode("utf-8"))

    with pytest.raises(GrantStoreError):
        GrantMetadataStore(path).load()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":"ths/grant-metadata/0.1","schema":"duplicate","grants":[]}',
        b'{"schema":"ths/grant-metadata/0.1","grants":NaN}',
        b"not-json",
        b"\xff",
        b"",
    ],
)
def test_duplicate_keys_nonfinite_and_malformed_json_fail_closed(tmp_path, raw):
    path = private_path(tmp_path)
    write_private(path, raw)
    with pytest.raises(GrantStoreError):
        GrantMetadataStore(path).load()


def test_invalid_snapshot_is_rejected_before_touching_previous_state(tmp_path):
    path = private_path(tmp_path)
    store = GrantMetadataStore(path)
    store.save([grant()])
    original = path.read_bytes()

    with pytest.raises(GrantStoreError):
        store.save([grant(credential_digest=SYNTHETIC_CREDENTIAL)])
    assert path.read_bytes() == original

    document = json.loads(original)
    document["grants"][0]["unexpected"] = True
    write_private(path, json.dumps(document).encode())
    corrupt = path.read_bytes()
    with pytest.raises(GrantStoreError):
        store.save([grant("g-synthetic-two")])
    assert path.read_bytes() == corrupt


def test_post_replace_directory_fsync_failure_restores_previous_snapshot(
    tmp_path, monkeypatch
):
    path = private_path(tmp_path)
    store = GrantMetadataStore(path)
    store.save([grant()])
    original = path.read_bytes()
    real_fsync = os.fsync
    directory_fsyncs = 0

    def fail_commit(descriptor: int) -> None:
        nonlocal directory_fsyncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs += 1
            if directory_fsyncs == 2:
                raise OSError("synthetic directory fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", fail_commit)
    with pytest.raises(GrantStoreError):
        store.save([grant("g-synthetic-two")])

    assert path.read_bytes() == original
    assert GrantMetadataStore(path).load()["g-synthetic-one"].name == (
        "Synthetic Test Agent"
    )
    assert not list(path.parent.glob(".grants-*.tmp"))


def test_failed_first_commit_leaves_no_live_store(tmp_path, monkeypatch):
    path = private_path(tmp_path)
    store = GrantMetadataStore(path)
    real_fsync = os.fsync
    directory_fsyncs = 0

    def fail_commit(descriptor: int) -> None:
        nonlocal directory_fsyncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs += 1
            if directory_fsyncs == 2:
                raise OSError("synthetic directory fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", fail_commit)
    with pytest.raises(GrantStoreError):
        store.save([grant()])
    assert not path.exists()


def test_symlink_hardlink_and_nonprivate_paths_are_rejected(tmp_path):
    real_directory = tmp_path / "real-private"
    real_directory.mkdir(mode=0o700)
    real_directory.chmod(0o700)
    real_file = real_directory / "real.json"
    GrantMetadataStore(real_file).save([grant()])

    link_directory = tmp_path / "linked-private"
    link_directory.symlink_to(real_directory, target_is_directory=True)
    with pytest.raises(GrantStoreError):
        GrantMetadataStore(link_directory / "grants.json").load()

    private = tmp_path / "other-private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    link_file = private / "linked.json"
    link_file.symlink_to(real_file)
    with pytest.raises(GrantStoreError):
        GrantMetadataStore(link_file).load()

    hardlink = private / "hardlinked.json"
    os.link(real_file, hardlink)
    with pytest.raises(GrantStoreError):
        GrantMetadataStore(hardlink).load()

    public_directory = tmp_path / "public"
    public_directory.mkdir(mode=0o755)
    public_directory.chmod(0o755)
    with pytest.raises(GrantStoreError):
        GrantMetadataStore(public_directory / "grants.json").save([grant()])


def test_nonprivate_existing_file_is_rejected_without_permission_repair(tmp_path):
    path = private_path(tmp_path)
    GrantMetadataStore(path).save([grant()])
    path.chmod(0o644)
    with pytest.raises(GrantStoreError):
        GrantMetadataStore(path).load()
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
