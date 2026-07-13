"""Synthetic end-to-end proof for THS-0022 → THS-0023."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from threshold.capture.geometry import RoomBinding, build_geometry
from threshold.housefile.materialize import MaterializationError, materialize_housefile
from threshold.housefile.store import HousefileStore


ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_FIXTURE = ROOT / "schema" / "examples" / "synthetic-demo-house.json"


def _proposal_digest(index: int) -> str:
    return hashlib.sha256(f"synthetic-proposal-{index}".encode("ascii")).hexdigest()


def test_explicit_geometry_review_materializes_one_synthetic_revision(
    tmp_path: Path,
) -> None:
    private = tmp_path / "unmistakably-synthetic-private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    canonical = private / "synthetic-house.json"
    source = json.loads(SYNTHETIC_FIXTURE.read_text(encoding="utf-8"))
    canonical.write_bytes(SYNTHETIC_FIXTURE.read_bytes())
    os.chmod(canonical, 0o600)

    bindings = [
        RoomBinding(
            zone_id=zone["id"],
            suggested_name=f"Untrusted model suggestion {index}",
            proposal_sha256=_proposal_digest(index),
        )
        for index, zone in enumerate(source["zones"])
    ]
    geometry = build_geometry(bindings)
    review_names = [f"Owner reviewed synthetic zone {index}" for index in range(len(bindings))]
    review = {
        "schema": "ths/materialization-review/0.1",
        "owner_reviewed": True,
        "synthetic_fixture": True,
        "expected_geometry_sha256": geometry.geometry_sha256,
        "expected_housefile_rev": "A",
        "zones": [
            {
                "order": index,
                "zone_id": zone["id"],
                "proposal_sha256": _proposal_digest(index),
                "name": review_names[index],
                "access": zone["access"],
                "outdoor": zone.get("outdoor", False),
            }
            for index, zone in enumerate(source["zones"])
        ],
    }

    receipt = materialize_housefile(canonical, geometry.canonical_bytes, review)
    restarted = HousefileStore(canonical).load()

    assert receipt.previous_rev == "A"
    assert receipt.new_rev == "B"
    assert receipt.geometry_sha256 == geometry.geometry_sha256
    assert receipt.zone_count == len(bindings)
    assert receipt.synthetic_fixture is True
    assert receipt.canonical_housefile_written is True
    assert restarted["rev"] == "B"
    assert [zone["name"] for zone in restarted["zones"]] == review_names
    assert [zone["access"] for zone in restarted["zones"]] == [
        zone["access"] for zone in source["zones"]
    ]
    assert [zone["outdoor"] for zone in restarted["zones"]] == [
        zone.get("outdoor", False) for zone in source["zones"]
    ]
    assert [zone["boundary"] for zone in restarted["zones"]] == [
        list(room.boundary) for room in geometry.rooms
    ]
    assert restarted["materialization"] == {
        "schema": "ths/materialization-provenance/0.1",
        "geometry_sha256": geometry.geometry_sha256,
        "algorithm": "ths/rectangular-strip-grid/0.1",
        "zones": [
            {
                "order": index,
                "zone_id": zone["id"],
                "proposal_sha256": _proposal_digest(index),
            }
            for index, zone in enumerate(source["zones"])
        ],
    }
    encoded_housefile = canonical.read_text(encoding="utf-8")
    assert "Untrusted model suggestion" not in encoded_housefile

    receipt_text = json.dumps(receipt.as_dict(), sort_keys=True)
    assert not any(name in receipt_text for name in review_names)
    assert str(private) not in receipt_text

    committed = canonical.read_bytes()
    with pytest.raises(MaterializationError) as caught:
        materialize_housefile(canonical, geometry.canonical_bytes, review)
    assert caught.value.failure == "stale_housefile_revision"
    assert canonical.read_bytes() == committed
