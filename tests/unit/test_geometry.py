from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from threshold.capture import geometry


def _bindings(count: int = 3) -> list[geometry.RoomBinding]:
    return [
        geometry.RoomBinding(
            zone_id=f"synthetic-zone-{index + 1}",
            suggested_name=f"Synthetic Room {index + 1}",
            proposal_sha256=f"{index + 1:064x}",
        )
        for index in range(count)
    ]


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _parse_changed(value: dict[str, object]) -> geometry.GeometryArtifact:
    data = _canonical(value)
    return geometry.parse_geometry(data, hashlib.sha256(data).hexdigest())


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _schema() -> dict[str, object]:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "ths-geometry-proposal-0.1.schema.json"
    )
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_geometry_is_deterministic_canonical_and_digest_bound():
    first = geometry.build_geometry(_bindings())
    second = geometry.build_geometry(tuple(_bindings()))

    assert first.canonical_bytes == second.canonical_bytes
    assert first.geometry_sha256 == second.geometry_sha256
    assert first.geometry_sha256 == hashlib.sha256(first.canonical_bytes).hexdigest()
    assert first.canonical_bytes == _canonical(first.as_dict())
    assert first.as_dict() == {
        "schema": "ths/geometry-proposal/0.1",
        "algorithm": "ths/rectangular-strip-grid/0.1",
        "rooms": [
            {
                "order": 0,
                "zone_id": "synthetic-zone-1",
                "suggested_name": "Synthetic Room 1",
                "proposal_sha256": f"{1:064x}",
                "zone_candidate_id": "zone-candidate-001",
                "boundary": [0, 0, 400, 300],
            },
            {
                "order": 1,
                "zone_id": "synthetic-zone-2",
                "suggested_name": "Synthetic Room 2",
                "proposal_sha256": f"{2:064x}",
                "zone_candidate_id": "zone-candidate-001",
                "boundary": [400, 0, 400, 300],
            },
            {
                "order": 2,
                "zone_id": "synthetic-zone-3",
                "suggested_name": "Synthetic Room 3",
                "proposal_sha256": f"{3:064x}",
                "zone_candidate_id": "zone-candidate-001",
                "boundary": [800, 0, 400, 300],
            },
        ],
        "canonical_housefile_written": False,
    }

    parsed = geometry.parse_geometry(first.canonical_bytes, first.geometry_sha256)
    assert parsed == first


def test_explicit_order_changes_digest_and_zone_coordinates():
    bindings = _bindings()
    original = geometry.build_geometry(bindings)
    reordered = geometry.build_geometry([bindings[1], bindings[0], bindings[2]])

    assert original.geometry_sha256 != reordered.geometry_sha256
    assert original.rooms[0].zone_id == "synthetic-zone-1"
    assert reordered.rooms[0].zone_id == "synthetic-zone-2"
    assert original.rooms[0].boundary == reordered.rooms[0].boundary == (0, 0, 400, 300)
    assert original.rooms[1].boundary == reordered.rooms[1].boundary == (400, 0, 400, 300)
    original_by_id = {room.zone_id: room.boundary for room in original.rooms}
    reordered_by_id = {room.zone_id: room.boundary for room in reordered.rooms}
    assert original_by_id["synthetic-zone-1"] != reordered_by_id["synthetic-zone-1"]


def test_strip_wraps_to_fixed_grid_without_dimension_inference():
    artifact = geometry.build_geometry(_bindings(64))

    assert artifact.rooms[7].boundary == (2800, 0, 400, 300)
    assert artifact.rooms[8].boundary == (0, 300, 400, 300)
    assert artifact.rooms[63].boundary == (2800, 2100, 400, 300)
    assert all(room.boundary[2:] == (400, 300) for room in artifact.rooms)


def test_geometry_digest_tamper_fails_closed():
    artifact = geometry.build_geometry(_bindings())

    with pytest.raises(geometry.GeometryValidationError) as caught:
        geometry.parse_geometry(artifact.canonical_bytes, "f" * 64)
    assert caught.value.reason == "geometry_digest_mismatch"

    tampered = artifact.canonical_bytes.replace(b"Synthetic Room 1", b"Synthetic Room X")
    with pytest.raises(geometry.GeometryValidationError) as caught:
        geometry.parse_geometry(tampered, artifact.geometry_sha256)
    assert caught.value.reason == "geometry_digest_mismatch"


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"{", "invalid_geometry_json"),
        (
            b'{"algorithm":"ths/rectangular-strip-grid/0.1",'
            b'"algorithm":"ths/rectangular-strip-grid/0.1"}\n',
            "duplicate_json_key",
        ),
        (b'{"value":NaN}\n', "nonfinite_json_number"),
        (b'{"value":Infinity}\n', "nonfinite_json_number"),
        (b"\xff", "invalid_geometry_json"),
    ],
)
def test_malformed_duplicate_and_nonfinite_json_is_rejected(data: bytes, reason: str):
    digest = hashlib.sha256(data).hexdigest()
    with pytest.raises(geometry.GeometryValidationError) as caught:
        geometry.parse_geometry(data, digest)
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unknown": True}),
        lambda value: value["rooms"][0].update({"unknown": True}),
        lambda value: value.update({"schema": "ths/geometry-proposal/9.9"}),
        lambda value: value.update({"algorithm": "model-selected-layout"}),
        lambda value: value.update({"canonical_housefile_written": True}),
        lambda value: value["rooms"][0].update({"order": 1}),
        lambda value: value["rooms"][0].update({"boundary": [1, 0, 400, 300]}),
        lambda value: value["rooms"][0].update({"boundary": [0.0, 0, 400, 300]}),
        lambda value: value["rooms"][0].update({"zone_candidate_id": "candidate-from-model"}),
        lambda value: value["rooms"].append(copy.deepcopy(value["rooms"][0])),
    ],
)
def test_strict_parser_rejects_unknown_or_semantically_changed_fields(mutate):
    value = geometry.build_geometry(_bindings()).as_dict()
    mutate(value)
    with pytest.raises(geometry.GeometryValidationError):
        _parse_changed(value)


@pytest.mark.parametrize(
    "field",
    ["access", "no-go", "outdoor", "policy", "grant", "command", "enforcement"],
)
def test_policy_or_control_fields_are_absent_and_rejected(field: str):
    value = geometry.build_geometry(_bindings()).as_dict()
    assert field not in _all_keys(value)

    value["rooms"][0][field] = "model-choice"
    with pytest.raises(geometry.GeometryValidationError) as caught:
        _parse_changed(value)
    assert caught.value.reason == "invalid_geometry_room"


@pytest.mark.parametrize(
    ("binding", "reason"),
    [
        (geometry.RoomBinding("UPPER", "Synthetic", "1" * 64), "invalid_zone_id"),
        (geometry.RoomBinding("dot.zone", "Synthetic", "1" * 64), "invalid_zone_id"),
        (geometry.RoomBinding("zone", " Synthetic", "1" * 64), "invalid_suggested_name"),
        (
            geometry.RoomBinding("zone", "Synthetic\nRoom", "1" * 64),
            "invalid_suggested_name",
        ),
        (geometry.RoomBinding("zone", "Cafe\u200b", "1" * 64), "invalid_suggested_name"),
        (geometry.RoomBinding("zone", "x" * 81, "1" * 64), "invalid_suggested_name"),
        (geometry.RoomBinding("zone", "Synthetic", "A" * 64), "invalid_proposal_digest"),
        (geometry.RoomBinding("zone", "Synthetic", "1" * 63), "invalid_proposal_digest"),
        (
            geometry.RoomBinding("zone", "Synthetic", "1" * 64, "zone-candidate-002"),
            "invalid_zone_candidate_id",
        ),
    ],
)
def test_binding_fields_are_strict_and_bounded(binding: geometry.RoomBinding, reason: str):
    with pytest.raises(geometry.GeometryValidationError) as caught:
        geometry.build_geometry([binding])
    assert caught.value.reason == reason


def test_room_count_type_and_zone_uniqueness_are_enforced():
    with pytest.raises(geometry.GeometryValidationError, match="invalid_room_count"):
        geometry.build_geometry([])
    with pytest.raises(geometry.GeometryValidationError, match="invalid_room_count"):
        geometry.build_geometry(_bindings(65))
    with pytest.raises(geometry.GeometryValidationError, match="invalid_room_bindings"):
        geometry.build_geometry("synthetic-zone")  # type: ignore[arg-type]
    with pytest.raises(geometry.GeometryValidationError, match="invalid_room_bindings"):
        geometry.build_geometry(iter(_bindings()))  # type: ignore[arg-type]
    with pytest.raises(geometry.GeometryValidationError, match="invalid_room_binding"):
        geometry.build_geometry([{"zone_id": "synthetic-zone"}])  # type: ignore[list-item]

    duplicate = _bindings(2)
    duplicate[1] = geometry.RoomBinding(
        zone_id=duplicate[0].zone_id,
        suggested_name="Another Synthetic Room",
        proposal_sha256="f" * 64,
    )
    with pytest.raises(geometry.GeometryValidationError, match="duplicate_zone_id"):
        geometry.build_geometry(duplicate)


def test_dishonest_sequence_cannot_escape_the_snapshot_bound():
    class EndlessSequence(Sequence[geometry.RoomBinding]):
        def __init__(self) -> None:
            self.reads = 0

        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> geometry.RoomBinding:
            del index
            self.reads += 1
            return _bindings(1)[0]

    bindings = EndlessSequence()
    with pytest.raises(geometry.GeometryValidationError, match="invalid_room_count"):
        geometry.build_geometry(bindings)
    assert bindings.reads == geometry.MAX_ROOMS + 1


def test_one_proposal_digest_cannot_bind_multiple_zones():
    duplicate = _bindings(2)
    duplicate[1] = geometry.RoomBinding(
        zone_id=duplicate[1].zone_id,
        suggested_name=duplicate[1].suggested_name,
        proposal_sha256=duplicate[0].proposal_sha256,
    )
    with pytest.raises(
        geometry.GeometryValidationError,
        match="duplicate_proposal_digest",
    ):
        geometry.build_geometry(duplicate)

    value = geometry.build_geometry(_bindings(2)).as_dict()
    value["rooms"][1]["proposal_sha256"] = value["rooms"][0]["proposal_sha256"]
    with pytest.raises(geometry.GeometryValidationError) as caught:
        _parse_changed(value)
    assert caught.value.reason == "duplicate_proposal_digest"


def test_parser_requires_lowercase_exact_digest_and_canonical_json():
    artifact = geometry.build_geometry(_bindings())
    with pytest.raises(geometry.GeometryValidationError, match="invalid_geometry_digest"):
        geometry.parse_geometry(artifact.canonical_bytes, artifact.geometry_sha256.upper())

    noncanonical = json.dumps(artifact.as_dict(), indent=2).encode("utf-8")
    with pytest.raises(geometry.GeometryValidationError) as caught:
        geometry.parse_geometry(noncanonical, hashlib.sha256(noncanonical).hexdigest())
    assert caught.value.reason == "noncanonical_geometry_json"


def test_public_schema_matches_artifact_shape_and_contains_no_policy_fields():
    schema = _schema()
    artifact = geometry.build_geometry(_bindings()).as_dict()

    assert schema["properties"]["schema"]["const"] == artifact["schema"]
    assert schema["properties"]["algorithm"]["const"] == artifact["algorithm"]
    assert schema["properties"]["rooms"]["minItems"] == 1
    assert schema["properties"]["rooms"]["maxItems"] == 64
    assert schema["additionalProperties"] is False
    assert schema["properties"]["rooms"]["items"]["additionalProperties"] is False
    assert {
        "access",
        "no-go",
        "outdoor",
        "policy",
        "grant",
        "command",
        "enforcement",
    }.isdisjoint(_all_keys(schema))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["rooms"][0].update(suggested_name=" Leading"),
        lambda value: value["rooms"][0].update(suggested_name="Trailing "),
        lambda value: value["rooms"][0].update(suggested_name="Line\nBreak"),
        lambda value: value["rooms"][0].update(suggested_name="Line\u2028Break"),
        lambda value: value["rooms"][0].update(boundary=[1, 0, 400, 300]),
        lambda value: value["rooms"][0].update(order=1),
        lambda value: value["rooms"][0].update(access="open"),
        lambda value: value.update(unexpected=True),
    ],
)
def test_draft_2020_12_schema_rejects_enforceable_invalid_artifacts(mutate):
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    artifact = geometry.build_geometry(_bindings()).as_dict()
    validator.validate(artifact)

    invalid = copy.deepcopy(artifact)
    mutate(invalid)
    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_schema_documents_parser_only_cross_field_guarantees():
    schema = _schema()
    comment = schema["properties"]["rooms"]["$comment"]
    assert "parse_geometry" in comment
    assert "unique zone_id and proposal_sha256" in comment
    assert "array-index-contiguous order" in comment

    validator = Draft202012Validator(schema)
    artifact = geometry.build_geometry(_bindings(2)).as_dict()
    reordered = copy.deepcopy(artifact)
    reordered["rooms"] = list(reversed(reordered["rooms"]))
    validator.validate(reordered)
    with pytest.raises(geometry.GeometryValidationError, match="invalid_geometry_room"):
        _parse_changed(reordered)


def test_schema_enforces_every_versioned_order_boundary_mapping():
    validator = Draft202012Validator(_schema())
    artifact = geometry.build_geometry(_bindings(64)).as_dict()
    validator.validate(artifact)

    invalid = copy.deepcopy(artifact)
    invalid["rooms"][63]["boundary"] = [2800, 1800, 400, 300]
    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_printable_unicode_suggested_name_round_trips_through_schema_and_parser():
    bindings = _bindings(1)
    bindings[0] = geometry.RoomBinding(
        zone_id=bindings[0].zone_id,
        suggested_name="Café synthétique",
        proposal_sha256=bindings[0].proposal_sha256,
    )
    artifact = geometry.build_geometry(bindings)

    Draft202012Validator(_schema()).validate(artifact.as_dict())
    assert (
        geometry.parse_geometry(artifact.canonical_bytes, artifact.geometry_sha256)
        == artifact
    )
