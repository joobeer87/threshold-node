"""Deterministic, policy-free rectangular geometry proposals for THS-0022.

The caller supplies an explicit room order and trusted local bindings to exact
vision-proposal digests.  This module only assigns fixed rectangles; it does
not infer or accept household policy and it never writes the housefile.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hmac import compare_digest
from itertools import islice
from typing import Any


GEOMETRY_SCHEMA = "ths/geometry-proposal/0.1"
ALGORITHM = "ths/rectangular-strip-grid/0.1"
ZONE_CANDIDATE_ID = "zone-candidate-001"

MAX_ROOMS = 64
MAX_NAME_LENGTH = 80
MAX_GEOMETRY_BYTES = 128 * 1024
GRID_COLUMNS = 8
ROOM_WIDTH = 400
ROOM_HEIGHT = 300

_SHA256 = re.compile(r"[0-9a-f]{64}")
_ZONE_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


class GeometryValidationError(ValueError):
    """A fixed, non-sensitive failure raised for invalid geometry input."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RoomBinding:
    """One locally chosen zone bound to one exact vision proposal."""

    zone_id: str
    suggested_name: str = field(repr=False)
    proposal_sha256: str
    zone_candidate_id: str = ZONE_CANDIDATE_ID


@dataclass(frozen=True)
class GeometryRoom:
    """One immutable, validated room projection from a geometry artifact."""

    order: int
    zone_id: str
    suggested_name: str = field(repr=False)
    proposal_sha256: str
    zone_candidate_id: str
    boundary: tuple[int, int, int, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "zone_id": self.zone_id,
            "suggested_name": self.suggested_name,
            "proposal_sha256": self.proposal_sha256,
            "zone_candidate_id": self.zone_candidate_id,
            "boundary": list(self.boundary),
        }


@dataclass(frozen=True)
class GeometryArtifact:
    """Canonical geometry bytes plus their exact SHA-256 binding."""

    canonical_bytes: bytes = field(repr=False)
    geometry_sha256: str
    rooms: tuple[GeometryRoom, ...] = field(repr=False)

    def as_dict(self) -> dict[str, object]:
        """Return a detached JSON-compatible representation."""

        return {
            "schema": GEOMETRY_SCHEMA,
            "algorithm": ALGORITHM,
            "rooms": [room.as_dict() for room in self.rooms],
            "canonical_housefile_written": False,
        }


def _fail(reason: str) -> None:
    raise GeometryValidationError(reason)


def _canonical_json(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise GeometryValidationError("geometry_not_serializable") from exc
    return (encoded + "\n").encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GeometryValidationError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise GeometryValidationError("nonfinite_json_number")


def _exact_keys(value: Mapping[str, object], expected: frozenset[str]) -> bool:
    return frozenset(value) == expected


def _valid_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 1 <= len(value) <= MAX_NAME_LENGTH
        and all(character.isprintable() for character in value)
    )


def _valid_zone_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 64
        and _ZONE_ID.fullmatch(value) is not None
    )


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _boundary(order: int) -> tuple[int, int, int, int]:
    return (
        (order % GRID_COLUMNS) * ROOM_WIDTH,
        (order // GRID_COLUMNS) * ROOM_HEIGHT,
        ROOM_WIDTH,
        ROOM_HEIGHT,
    )


def _validated_binding(binding: object, order: int) -> GeometryRoom:
    if not isinstance(binding, RoomBinding):
        _fail("invalid_room_binding")
    if not _valid_zone_id(binding.zone_id):
        _fail("invalid_zone_id")
    if not _valid_name(binding.suggested_name):
        _fail("invalid_suggested_name")
    if not _valid_digest(binding.proposal_sha256):
        _fail("invalid_proposal_digest")
    if binding.zone_candidate_id != ZONE_CANDIDATE_ID:
        _fail("invalid_zone_candidate_id")
    return GeometryRoom(
        order=order,
        zone_id=binding.zone_id,
        suggested_name=binding.suggested_name,
        proposal_sha256=binding.proposal_sha256,
        zone_candidate_id=ZONE_CANDIDATE_ID,
        boundary=_boundary(order),
    )


def _artifact(rooms: tuple[GeometryRoom, ...]) -> GeometryArtifact:
    document = {
        "schema": GEOMETRY_SCHEMA,
        "algorithm": ALGORITHM,
        "rooms": [room.as_dict() for room in rooms],
        "canonical_housefile_written": False,
    }
    canonical_bytes = _canonical_json(document)
    return GeometryArtifact(
        canonical_bytes=canonical_bytes,
        geometry_sha256=hashlib.sha256(canonical_bytes).hexdigest(),
        rooms=rooms,
    )


def build_geometry(bindings: Sequence[RoomBinding]) -> GeometryArtifact:
    """Build a canonical proposal from an explicit, significant room order."""

    if isinstance(bindings, (str, bytes, bytearray)) or not isinstance(
        bindings, Sequence
    ):
        _fail("invalid_room_bindings")
    try:
        count = len(bindings)
    except Exception as exc:
        raise GeometryValidationError("invalid_room_bindings") from exc
    if not 1 <= count <= MAX_ROOMS:
        _fail("invalid_room_count")
    try:
        # A hostile Sequence may lie about ``len`` and yield forever.  Snapshot
        # no more than one value beyond the public limit before comparing its
        # declared and observed sizes.
        values = tuple(islice(iter(bindings), MAX_ROOMS + 1))
    except Exception as exc:
        raise GeometryValidationError("invalid_room_bindings") from exc
    if len(values) > MAX_ROOMS:
        _fail("invalid_room_count")
    if len(values) != count:
        _fail("room_bindings_changed")

    rooms = tuple(
        _validated_binding(binding, order)
        for order, binding in enumerate(values)
    )
    zone_ids = [room.zone_id for room in rooms]
    if len(set(zone_ids)) != len(zone_ids):
        _fail("duplicate_zone_id")
    proposal_digests = [room.proposal_sha256 for room in rooms]
    if len(set(proposal_digests)) != len(proposal_digests):
        _fail("duplicate_proposal_digest")
    return _artifact(rooms)


def _parse_json(data: bytes) -> object:
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_GEOMETRY_BYTES:
        _fail("invalid_geometry_bytes")
    try:
        text = data.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except GeometryValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise GeometryValidationError("invalid_geometry_json") from exc


def _validate_document(value: object) -> tuple[GeometryRoom, ...]:
    if not isinstance(value, dict) or not _exact_keys(
        value,
        frozenset({"schema", "algorithm", "rooms", "canonical_housefile_written"}),
    ):
        _fail("invalid_geometry_document")
    if (
        value["schema"] != GEOMETRY_SCHEMA
        or value["algorithm"] != ALGORITHM
        or value["canonical_housefile_written"] is not False
    ):
        _fail("invalid_geometry_document")

    raw_rooms = value["rooms"]
    if not isinstance(raw_rooms, list) or not 1 <= len(raw_rooms) <= MAX_ROOMS:
        _fail("invalid_room_count")

    rooms: list[GeometryRoom] = []
    zone_ids: set[str] = set()
    proposal_digests: set[str] = set()
    expected_keys = frozenset(
        {
            "order",
            "zone_id",
            "suggested_name",
            "proposal_sha256",
            "zone_candidate_id",
            "boundary",
        }
    )
    for order, raw_room in enumerate(raw_rooms):
        if not isinstance(raw_room, dict) or not _exact_keys(raw_room, expected_keys):
            _fail("invalid_geometry_room")
        if (
            not isinstance(raw_room["order"], int)
            or isinstance(raw_room["order"], bool)
            or raw_room["order"] != order
            or not _valid_zone_id(raw_room["zone_id"])
            or not _valid_name(raw_room["suggested_name"])
            or not _valid_digest(raw_room["proposal_sha256"])
            or raw_room["zone_candidate_id"] != ZONE_CANDIDATE_ID
        ):
            _fail("invalid_geometry_room")
        expected_boundary = _boundary(order)
        raw_boundary = raw_room["boundary"]
        if (
            not isinstance(raw_boundary, list)
            or len(raw_boundary) != 4
            or any(
                not isinstance(number, int) or isinstance(number, bool)
                for number in raw_boundary
            )
            or tuple(raw_boundary) != expected_boundary
        ):
            _fail("invalid_geometry_boundary")
        zone_id = raw_room["zone_id"]
        if zone_id in zone_ids:
            _fail("duplicate_zone_id")
        zone_ids.add(zone_id)
        proposal_digest = raw_room["proposal_sha256"]
        if proposal_digest in proposal_digests:
            _fail("duplicate_proposal_digest")
        proposal_digests.add(proposal_digest)
        rooms.append(
            GeometryRoom(
                order=order,
                zone_id=zone_id,
                suggested_name=raw_room["suggested_name"],
                proposal_sha256=proposal_digest,
                zone_candidate_id=ZONE_CANDIDATE_ID,
                boundary=expected_boundary,
            )
        )
    return tuple(rooms)


def parse_geometry(data: bytes, expected_geometry_sha256: str) -> GeometryArtifact:
    """Verify an exact digest, canonical encoding, schema, and layout semantics."""

    if not _valid_digest(expected_geometry_sha256):
        _fail("invalid_geometry_digest")
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_GEOMETRY_BYTES:
        _fail("invalid_geometry_bytes")
    actual_digest = hashlib.sha256(data).hexdigest()
    if not compare_digest(actual_digest, expected_geometry_sha256):
        _fail("geometry_digest_mismatch")

    value = _parse_json(data)
    rooms = _validate_document(value)
    artifact = _artifact(rooms)
    if artifact.canonical_bytes != data:
        _fail("noncanonical_geometry_json")
    if not compare_digest(artifact.geometry_sha256, expected_geometry_sha256):
        _fail("geometry_digest_mismatch")
    return artifact
