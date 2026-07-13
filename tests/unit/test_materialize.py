"""Adversarial proof for THS-0023 synthetic-only materialization."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from threshold.housefile.materialize import MaterializationError, materialize_housefile
from threshold.housefile.store import (
    HousefileStore,
    HousefileStoreError,
    THS_SCHEMA_RESOURCE,
    canonical_json,
    parse_json_bytes,
    save,
    validate_ths_document,
)


P1 = "1" * 64
P2 = "2" * 64


def _document(*, rev: str = "A") -> dict[str, object]:
    return {
        "schema": "ths/0.1",
        "rev": rev,
        "fixture": {
            "synthetic": True,
            "notice": "Synthetic temporary test fixture only.",
        },
        "dwelling": {"name": "Synthetic Temporary House", "type": "synthetic"},
        "zones": [
            {
                "id": "old-zone",
                "name": "Old synthetic zone",
                "access": "open",
                "boundary": [0, 0, 1, 1],
            }
        ],
        "policies": {
            "quietHours": {"start": "21:30", "end": "06:30", "timezone": "Etc/UTC"},
            "teleop": "per-session",
            "residency": "local-first",
        },
    }


def _write_document(path: Path, document: dict[str, object] | None = None) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_bytes(canonical_json(document or _document()))
    os.chmod(path, 0o600)


def _geometry(
    rooms: list[tuple[str, str, str]] | None = None,
) -> tuple[bytes, str]:
    selected = rooms or [("owner-zone", "Model suggested name", P1)]
    artifact = {
        "schema": "ths/geometry-proposal/0.1",
        "algorithm": "ths/rectangular-strip-grid/0.1",
        "rooms": [
            {
                "order": index,
                "zone_id": zone_id,
                "suggested_name": suggested_name,
                "proposal_sha256": proposal_digest,
                "zone_candidate_id": "zone-candidate-001",
                "boundary": [(index % 8) * 400, (index // 8) * 300, 400, 300],
            }
            for index, (zone_id, suggested_name, proposal_digest) in enumerate(selected)
        ],
        "canonical_housefile_written": False,
    }
    encoded = canonical_json(artifact)
    return encoded, hashlib.sha256(encoded).hexdigest()


def _review(
    digest: str,
    *,
    rev: str = "A",
    zones: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema": "ths/materialization-review/0.1",
        "owner_reviewed": True,
        "synthetic_fixture": True,
        "expected_geometry_sha256": digest,
        "expected_housefile_rev": rev,
        "zones": zones
        or [
            {
                "order": 0,
                "zone_id": "owner-zone",
                "proposal_sha256": P1,
                "name": "Owner reviewed name",
                "access": "no-go",
                "outdoor": True,
            }
        ],
    }


def _failure(path: Path, geometry: bytes, review: bytes | dict[str, object]) -> str:
    with pytest.raises(MaterializationError) as caught:
        materialize_housefile(path, geometry, review)
    return caught.value.failure


def test_materializes_exact_owner_policy_and_sanitized_provenance(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()

    receipt = materialize_housefile(path, geometry, _review(digest))
    stored = parse_json_bytes(path.read_bytes())

    assert stored["rev"] == "B"
    assert stored["zones"] == [
        {
            "id": "owner-zone",
            "name": "Owner reviewed name",
            "access": "no-go",
            "boundary": [0, 0, 400, 300],
            "outdoor": True,
        }
    ]
    assert "Model suggested name" not in path.read_text(encoding="utf-8")
    assert stored["materialization"] == {
        "schema": "ths/materialization-provenance/0.1",
        "geometry_sha256": digest,
        "algorithm": "ths/rectangular-strip-grid/0.1",
        "zones": [{"order": 0, "zone_id": "owner-zone", "proposal_sha256": P1}],
    }
    expected_bindings = hashlib.sha256(
        canonical_json([{"order": 0, "zone_id": "owner-zone", "proposal_sha256": P1}])
    ).hexdigest()
    assert receipt.as_dict() == {
        "schema": "ths/materialization-receipt/0.1",
        "status": "passed",
        "previous_rev": "A",
        "new_rev": "B",
        "geometry_sha256": digest,
        "proposal_bindings_sha256": expected_bindings,
        "housefile_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "zone_count": 1,
        "synthetic_fixture": True,
        "canonical_housefile_written": True,
    }
    assert stat_mode(path) == 0o600
    assert stat_mode(path.parent) == 0o700


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_rejects_missing_or_extra_choice_coverage_without_write(
    tmp_path: Path, change: str
) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    rooms = [("first", "First", P1), ("second", "Second", P2)]
    geometry, digest = _geometry(rooms)
    zones = [
        {
            "order": index,
            "zone_id": zone_id,
            "proposal_sha256": proposal,
            "name": f"Owner {zone_id}",
            "access": "open",
            "outdoor": False,
        }
        for index, (zone_id, _name, proposal) in enumerate(rooms)
    ]
    if change == "missing":
        zones.pop()
    else:
        zones.append(
            {
                "order": 2,
                "zone_id": "extra",
                "proposal_sha256": "3" * 64,
                "name": "Extra",
                "access": "open",
                "outdoor": False,
            }
        )
    before = path.read_bytes()
    assert _failure(path, geometry, _review(digest, zones=zones)) == "review_choice_coverage_mismatch"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("expected_geometry_sha256", "f" * 64, "stale_geometry_digest"),
        ("expected_housefile_rev", "B", "stale_housefile_revision"),
    ],
)
def test_rejects_stale_geometry_or_revision(
    tmp_path: Path, field: str, value: object, expected: str
) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()
    review = _review(digest)
    review[field] = value
    before = path.read_bytes()
    assert _failure(path, geometry, review) == expected
    assert path.read_bytes() == before


def test_rejects_oversized_geometry_before_digest_comparison(tmp_path: Path) -> None:
    from threshold.capture.geometry import MAX_GEOMETRY_BYTES

    path = tmp_path / "private" / "house.json"
    _write_document(path)
    _geometry_bytes, digest = _geometry()
    before = path.read_bytes()

    assert (
        _failure(path, b"x" * (MAX_GEOMETRY_BYTES + 1), _review(digest))
        == "invalid_geometry"
    )
    assert path.read_bytes() == before


def test_rejects_mismatched_proposal_digest_and_zone_binding(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()
    for field, value in (("proposal_sha256", P2), ("zone_id", "different-zone")):
        review = _review(digest)
        review["zones"][0][field] = value  # type: ignore[index]
        assert _failure(path, geometry, review) == "review_choice_binding_mismatch"


def test_duplicate_proposal_digest_is_rejected_by_review_and_geometry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry([("first", "First", P1), ("second", "Second", P1)])
    zones = [
        {
            "order": index,
            "zone_id": zone_id,
            "proposal_sha256": P1,
            "name": f"Reviewed {zone_id}",
            "access": "open",
            "outdoor": False,
        }
        for index, zone_id in enumerate(("first", "second"))
    ]
    assert _failure(path, geometry, _review(digest, zones=zones)) == "invalid_review_payload"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda review: review.pop("owner_reviewed"),
        lambda review: review.update(owner_reviewed=False),
        lambda review: review.update(unexpected=True),
        lambda review: review["zones"][0].update(access="owner-only"),
        lambda review: review["zones"][0].update(outdoor=1),
        lambda review: review["zones"][0].update(name=" Model name "),
        lambda review: review["zones"][0].update(name="Owner\nname"),
        lambda review: review["zones"].append(deepcopy(review["zones"][0])),
        lambda review: review["zones"][0].update(order=True),
        lambda review: review["zones"][0].update(score=float("nan")),
    ],
)
def test_rejects_unknown_missing_duplicate_or_nonfinite_review_fields(
    tmp_path: Path, mutate
) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()
    review = _review(digest)
    mutate(review)
    assert _failure(path, geometry, review) == "invalid_review_payload"


def test_rejects_duplicate_json_keys_in_serialized_review(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()
    encoded = json.dumps(_review(digest), separators=(",", ":"))
    duplicate = encoded.replace(
        '"owner_reviewed":true', '"owner_reviewed":true,"owner_reviewed":true'
    ).encode()
    assert _failure(path, geometry, duplicate) == "invalid_review_payload"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.update(schema="ths/9.9"),
        lambda document: document.update(unknown=True),
        lambda document: document["policies"]["quietHours"].pop("timezone"),
    ],
)
def test_rejects_invalid_existing_schema(tmp_path: Path, mutate) -> None:
    path = tmp_path / "private" / "house.json"
    document = _document()
    mutate(document)
    _write_document(path, document)
    geometry, digest = _geometry()
    assert _failure(path, geometry, _review(digest)) == "invalid_housefile_schema"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document["fixture"].update(synthetic=False),
        lambda document: document["fixture"].update(notice="Temporary fixture only."),
        lambda document: document["dwelling"].update(name="Demo House"),
        lambda document: document["dwelling"].update(type="house"),
    ],
)
def test_never_materializes_non_synthetic_document(tmp_path: Path, mutate) -> None:
    path = tmp_path / "private" / "house.json"
    document = _document()
    mutate(document)
    _write_document(path, document)
    geometry, digest = _geometry()
    failure = _failure(path, geometry, _review(digest))
    assert failure in {"invalid_housefile_schema", "synthetic_fixture_required"}


def test_general_ths_schema_still_allows_non_fixture_private_documents() -> None:
    document = _document()
    del document["fixture"]
    document["dwelling"] = {"name": "Private dwelling", "type": "residence"}
    validate_ths_document(document)


def test_rejects_dangling_canonical_references(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    document = _document()
    document["inventory"] = [{"id": "i1", "name": "Synthetic item", "zone": "old-zone"}]
    _write_document(path, document)
    geometry, digest = _geometry()
    assert _failure(path, geometry, _review(digest)) == "invalid_housefile_references"


def test_rejects_duplicate_existing_identifiers(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    document = _document()
    document["zones"].append(deepcopy(document["zones"][0]))
    _write_document(path, document)
    geometry, digest = _geometry()
    assert _failure(path, geometry, _review(digest)) == "duplicate_housefile_identifier"


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "mode", "directory_mode"])
def test_rejects_unsafe_target_or_directory(tmp_path: Path, attack: str) -> None:
    private = tmp_path / "private"
    path = private / "house.json"
    _write_document(path)
    geometry, digest = _geometry()
    if attack == "symlink":
        real = private / "real.json"
        path.rename(real)
        path.symlink_to(real)
    elif attack == "hardlink":
        os.link(path, private / "other.json")
    elif attack == "mode":
        os.chmod(path, 0o640)
    else:
        os.chmod(private, 0o750)
    failure = _failure(path, geometry, _review(digest))
    assert failure in {
        "housefile_unavailable",
        "unsafe_housefile_file",
        "unsafe_housefile_directory",
    }


def test_rejects_unsafe_stable_lock(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    lock = path.parent / ".house.json.lock"
    lock.write_bytes(b"")
    os.chmod(lock, 0o644)
    geometry, digest = _geometry()
    assert _failure(path, geometry, _review(digest)) == "unsafe_housefile_lock"


def test_rejects_symlinked_parent_component(tmp_path: Path) -> None:
    real = tmp_path / "real-private"
    path = real / "house.json"
    _write_document(path)
    alias = tmp_path / "private-alias"
    alias.symlink_to(real, target_is_directory=True)
    geometry, digest = _geometry()
    assert _failure(alias / "house.json", geometry, _review(digest)) == "unsafe_housefile_path"


def test_rejects_paths_not_owned_by_effective_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threshold.housefile.store as store_module

    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()
    actual_euid = os.geteuid()
    monkeypatch.setattr(store_module.os, "geteuid", lambda: actual_euid + 1)
    assert _failure(path, geometry, _review(digest)) == "unsafe_housefile_directory"


def test_post_replace_fsync_failure_rolls_back_exact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threshold.housefile.store as store_module

    path = tmp_path / "private" / "house.json"
    _write_document(path)
    before = path.read_bytes()
    geometry, digest = _geometry()

    def fail_fsync(_path: Path) -> None:
        raise OSError("synthetic fsync fault")

    monkeypatch.setattr(store_module, "_fsync_directory", fail_fsync)
    assert _failure(path, geometry, _review(digest)) == "housefile_commit_failed"
    assert path.read_bytes() == before


def test_concurrent_expected_revision_is_cas_inside_lock(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()

    def attempt() -> str:
        try:
            materialize_housefile(path, geometry, _review(digest))
        except MaterializationError as exc:
            return exc.failure
        return "passed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda _index: attempt(), range(2)))
    assert outcomes == ["passed", "stale_housefile_revision"]
    assert parse_json_bytes(path.read_bytes())["rev"] == "B"


def test_revision_increment_is_deterministic_across_z(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path, _document(rev="Z"))
    geometry, digest = _geometry()
    receipt = materialize_housefile(path, geometry, _review(digest, rev="Z"))
    assert receipt.previous_rev == "Z"
    assert receipt.new_rev == "AA"


def test_revision_exhaustion_fails_without_write(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path, _document(rev="ZZZZZZZZ"))
    before = path.read_bytes()
    geometry, digest = _geometry()

    assert (
        _failure(path, geometry, _review(digest, rev="ZZZZZZZZ"))
        == "housefile_revision_exhausted"
    )
    assert path.read_bytes() == before


def test_requires_existing_canonical_document(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    geometry, digest = _geometry()
    assert _failure(private / "missing.json", geometry, _review(digest)) == "housefile_unavailable"
    assert not (private / ".missing.json.lock").exists()


def test_legacy_direct_save_is_fail_closed_without_touching_target(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    before = path.read_bytes()
    with pytest.raises(HousefileStoreError, match="direct_housefile_write_forbidden"):
        save(path, _document(rev="B"))
    assert path.read_bytes() == before


def test_internal_raw_replace_requires_an_active_store_lock(tmp_path: Path) -> None:
    path = tmp_path / "private" / "house.json"
    _write_document(path)
    before = path.read_bytes()
    store = HousefileStore(path)

    assert not hasattr(store, "replace_existing_locked")
    with pytest.raises(HousefileStoreError, match="housefile_lock_required"):
        store._replace_existing_locked(canonical_json({"bypass": True}))
    assert path.read_bytes() == before


def test_packaged_schema_projection_matches_public_canonical_schema() -> None:
    public_schema = Path(__file__).resolve().parents[2] / "schema" / "ths-0.1.schema.json"
    assert THS_SCHEMA_RESOURCE.read_bytes() == public_schema.read_bytes()


def test_schema_validation_fails_closed_when_validator_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    path = tmp_path / "private" / "house.json"
    _write_document(path)
    geometry, digest = _geometry()
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "jsonschema":
            raise ImportError("synthetic unavailable dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert _failure(path, geometry, _review(digest)) == "schema_validator_unavailable"
