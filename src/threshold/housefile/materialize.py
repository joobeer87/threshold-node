"""THS-0023 — explicit, digest-bound synthetic housefile materialization.

Geometry is observation-derived data, never policy.  This boundary accepts only
an exact owner-review payload and writes owner-selected names, access levels and
outdoor flags.  It never reads access or outdoor suggestions from a proposal.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path

from threshold.capture.geometry import MAX_GEOMETRY_BYTES, parse_geometry
from threshold.housefile.store import (
    HousefileStore,
    HousefileStoreError,
    canonical_json,
    parse_json_bytes,
    validate_ths_document,
)


REVIEW_SCHEMA = "ths/materialization-review/0.1"
PROVENANCE_SCHEMA = "ths/materialization-provenance/0.1"
RECEIPT_SCHEMA = "ths/materialization-receipt/0.1"
GEOMETRY_SCHEMA = "ths/geometry-proposal/0.1"
GEOMETRY_ALGORITHM = "ths/rectangular-strip-grid/0.1"
MAX_ZONES = 64

_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[A-Z]{1,8}")
_ZONE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")
_ACCESS = frozenset({"open", "restricted", "no-go"})


class MaterializationError(RuntimeError):
    """Fixed-code rejection that never contains a housefile body or path."""

    def __init__(self, failure: str) -> None:
        super().__init__(failure)
        self.failure = failure


@dataclass(frozen=True)
class ReviewedZone:
    order: int
    zone_id: str
    proposal_sha256: str
    name: str
    access: str
    outdoor: bool


@dataclass(frozen=True)
class MaterializationReview:
    expected_geometry_sha256: str
    expected_housefile_rev: str
    zones: tuple[ReviewedZone, ...]


@dataclass(frozen=True)
class MaterializationReceipt:
    schema: str
    status: str
    previous_rev: str
    new_rev: str
    geometry_sha256: str
    proposal_bindings_sha256: str
    housefile_sha256: str
    zone_count: int
    synthetic_fixture: bool
    canonical_housefile_written: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "previous_rev": self.previous_rev,
            "new_rev": self.new_rev,
            "geometry_sha256": self.geometry_sha256,
            "proposal_bindings_sha256": self.proposal_bindings_sha256,
            "housefile_sha256": self.housefile_sha256,
            "zone_count": self.zone_count,
            "synthetic_fixture": self.synthetic_fixture,
            "canonical_housefile_written": self.canonical_housefile_written,
        }


def _mapping_input(value: bytes | Mapping[str, object], failure: str) -> dict[str, object]:
    try:
        if isinstance(value, bytes):
            return parse_json_bytes(value)
        if not isinstance(value, Mapping):
            raise HousefileStoreError("invalid_housefile_json")
        # Canonical round-trip rejects non-string keys, non-finite numbers and
        # non-JSON objects while detaching the caller's mutable input.
        return parse_json_bytes(canonical_json(value))
    except HousefileStoreError as exc:
        raise MaterializationError(failure) from exc


def _exact_keys(value: Mapping[str, object], expected: set[str], failure: str) -> None:
    if set(value) != expected:
        raise MaterializationError(failure)


def _review(value: bytes | Mapping[str, object]) -> MaterializationReview:
    payload = _mapping_input(value, "invalid_review_payload")
    _exact_keys(
        payload,
        {
            "schema",
            "owner_reviewed",
            "synthetic_fixture",
            "expected_geometry_sha256",
            "expected_housefile_rev",
            "zones",
        },
        "invalid_review_payload",
    )
    geometry_digest = payload["expected_geometry_sha256"]
    expected_rev = payload["expected_housefile_rev"]
    zones_value = payload["zones"]
    if (
        payload["schema"] != REVIEW_SCHEMA
        or payload["owner_reviewed"] is not True
        or payload["synthetic_fixture"] is not True
        or not isinstance(geometry_digest, str)
        or _SHA256.fullmatch(geometry_digest) is None
        or not isinstance(expected_rev, str)
        or _REVISION.fullmatch(expected_rev) is None
        or not isinstance(zones_value, list)
        or not 1 <= len(zones_value) <= MAX_ZONES
    ):
        raise MaterializationError("invalid_review_payload")

    zones: list[ReviewedZone] = []
    ids: set[str] = set()
    proposal_digests: set[str] = set()
    for expected_order, item in enumerate(zones_value):
        if not isinstance(item, dict):
            raise MaterializationError("invalid_review_payload")
        _exact_keys(
            item,
            {"order", "zone_id", "proposal_sha256", "name", "access", "outdoor"},
            "invalid_review_payload",
        )
        order = item["order"]
        zone_id = item["zone_id"]
        proposal_digest = item["proposal_sha256"]
        name = item["name"]
        access = item["access"]
        outdoor = item["outdoor"]
        if (
            isinstance(order, bool)
            or not isinstance(order, int)
            or order != expected_order
            or not isinstance(zone_id, str)
            or _ZONE_ID.fullmatch(zone_id) is None
            or not isinstance(proposal_digest, str)
            or _SHA256.fullmatch(proposal_digest) is None
            or not isinstance(name, str)
            or not 1 <= len(name) <= 80
            or name != name.strip()
            or not all(character.isprintable() for character in name)
            or not isinstance(access, str)
            or access not in _ACCESS
            or not isinstance(outdoor, bool)
            or zone_id in ids
            or proposal_digest in proposal_digests
        ):
            raise MaterializationError("invalid_review_payload")
        ids.add(zone_id)
        proposal_digests.add(proposal_digest)
        zones.append(
            ReviewedZone(
                order=order,
                zone_id=zone_id,
                proposal_sha256=proposal_digest,
                name=name,
                access=access,
                outdoor=outdoor,
            )
        )
    return MaterializationReview(
        expected_geometry_sha256=geometry_digest,
        expected_housefile_rev=expected_rev,
        zones=tuple(zones),
    )


def _next_revision(revision: str) -> str:
    if _REVISION.fullmatch(revision) is None:
        raise MaterializationError("invalid_housefile_revision")
    values = [ord(char) - ord("A") for char in revision]
    index = len(values) - 1
    carry = 1
    while index >= 0 and carry:
        value = values[index] + carry
        values[index] = value % 26
        carry = value // 26
        index -= 1
    if carry:
        values.insert(0, 0)
    if len(values) > 8:
        raise MaterializationError("housefile_revision_exhausted")
    return "".join(chr(value + ord("A")) for value in values)


def _require_synthetic(document: Mapping[str, object]) -> None:
    fixture = document.get("fixture")
    dwelling = document.get("dwelling")
    if not isinstance(fixture, dict) or not isinstance(dwelling, dict):
        raise MaterializationError("synthetic_fixture_required")
    notice = fixture.get("notice")
    name = dwelling.get("name")
    if (
        fixture.get("synthetic") is not True
        or dwelling.get("type") != "synthetic"
        or not isinstance(notice, str)
        or not any(marker in notice.casefold() for marker in ("synthetic", "fictional", "demo"))
        or not isinstance(name, str)
        or "synthetic" not in name.casefold()
    ):
        raise MaterializationError("synthetic_fixture_required")


def _check_document_semantics(document: Mapping[str, object]) -> None:
    zones = document.get("zones")
    if not isinstance(zones, list):
        raise MaterializationError("invalid_housefile_schema")
    zone_ids: set[str] = set()
    for zone in zones:
        if not isinstance(zone, dict) or not isinstance(zone.get("id"), str):
            raise MaterializationError("invalid_housefile_schema")
        zone_id = zone["id"]
        if zone_id in zone_ids:
            raise MaterializationError("duplicate_housefile_identifier")
        zone_ids.add(zone_id)

    for collection in ("systems", "inventory", "quirks"):
        items = document.get(collection, [])
        if not isinstance(items, list):
            raise MaterializationError("invalid_housefile_schema")
        item_ids: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise MaterializationError("invalid_housefile_schema")
            item_id = item["id"]
            if item_id in item_ids:
                raise MaterializationError("duplicate_housefile_identifier")
            item_ids.add(item_id)
            if item.get("zone") not in zone_ids:
                raise MaterializationError("invalid_housefile_references")


def _schema_validate(document: Mapping[str, object]) -> None:
    try:
        validate_ths_document(document)
    except HousefileStoreError as exc:
        raise MaterializationError(exc.failure) from exc


def materialize_housefile(
    path: str | Path,
    geometry_bytes: bytes,
    review_payload: bytes | Mapping[str, object],
) -> MaterializationReceipt:
    """Materialize an exact reviewed geometry into an existing synthetic THS file."""

    review = _review(review_payload)
    if (
        not isinstance(geometry_bytes, bytes)
        or not 1 <= len(geometry_bytes) <= MAX_GEOMETRY_BYTES
    ):
        raise MaterializationError("invalid_geometry")
    actual_geometry_digest = hashlib.sha256(geometry_bytes).hexdigest()
    if not compare_digest(actual_geometry_digest, review.expected_geometry_sha256):
        raise MaterializationError("stale_geometry_digest")
    try:
        geometry = parse_geometry(
            geometry_bytes,
            expected_geometry_sha256=review.expected_geometry_sha256,
        )
        envelope = geometry.as_dict()
    except Exception as exc:
        raise MaterializationError("invalid_geometry") from exc
    if (
        envelope.get("schema") != GEOMETRY_SCHEMA
        or envelope.get("algorithm") != GEOMETRY_ALGORITHM
        or envelope.get("canonical_housefile_written") is not False
    ):
        raise MaterializationError("invalid_geometry")
    geometry_rooms = envelope.get("rooms")
    if not isinstance(geometry_rooms, list) or len(geometry_rooms) != len(review.zones):
        raise MaterializationError("review_choice_coverage_mismatch")

    canonical_zones: list[dict[str, object]] = []
    provenance_zones: list[dict[str, object]] = []
    for reviewed, room in zip(review.zones, geometry_rooms, strict=True):
        if not isinstance(room, dict):
            raise MaterializationError("invalid_geometry")
        if (
            room.get("order") != reviewed.order
            or room.get("zone_id") != reviewed.zone_id
            or room.get("proposal_sha256") != reviewed.proposal_sha256
        ):
            raise MaterializationError("review_choice_binding_mismatch")
        boundary = room.get("boundary")
        if not isinstance(boundary, list):
            raise MaterializationError("invalid_geometry")
        canonical_zones.append(
            {
                "id": reviewed.zone_id,
                "name": reviewed.name,
                "access": reviewed.access,
                "boundary": copy.deepcopy(boundary),
                "outdoor": reviewed.outdoor,
            }
        )
        provenance_zones.append(
            {
                "order": reviewed.order,
                "zone_id": reviewed.zone_id,
                "proposal_sha256": reviewed.proposal_sha256,
            }
        )

    bindings_digest = hashlib.sha256(canonical_json(provenance_zones)).hexdigest()
    store = HousefileStore(path)
    try:
        with store.locked():
            current = store.read_document_locked()
            _schema_validate(current)
            _require_synthetic(current)
            _check_document_semantics(current)
            current_rev = current.get("rev")
            if not isinstance(current_rev, str):
                raise MaterializationError("invalid_housefile_revision")
            if current_rev != review.expected_housefile_rev:
                raise MaterializationError("stale_housefile_revision")

            next_rev = _next_revision(current_rev)
            updated = copy.deepcopy(current)
            updated["rev"] = next_rev
            updated["zones"] = canonical_zones
            updated["materialization"] = {
                "schema": PROVENANCE_SCHEMA,
                "geometry_sha256": review.expected_geometry_sha256,
                "algorithm": GEOMETRY_ALGORITHM,
                "zones": provenance_zones,
            }
            _check_document_semantics(updated)
            _schema_validate(updated)
            final_bytes = canonical_json(updated)
            housefile_digest = hashlib.sha256(final_bytes).hexdigest()
            store._replace_existing_locked(final_bytes)
    except MaterializationError:
        raise
    except HousefileStoreError as exc:
        raise MaterializationError(exc.failure) from exc

    return MaterializationReceipt(
        schema=RECEIPT_SCHEMA,
        status="passed",
        previous_rev=review.expected_housefile_rev,
        new_rev=next_rev,
        geometry_sha256=review.expected_geometry_sha256,
        proposal_bindings_sha256=bindings_digest,
        housefile_sha256=housefile_digest,
        zone_count=len(review.zones),
        synthetic_fixture=True,
        canonical_housefile_written=True,
    )
