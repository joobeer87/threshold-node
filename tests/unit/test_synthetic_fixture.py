"""The public demo fixture must be valid and unambiguously synthetic."""

import json
from copy import deepcopy
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

from threshold.capture.seed import SEED_FILE


ROOT = Path(__file__).resolve().parents[2]


def test_public_fixture_validates_and_is_synthetic():
    schema = json.loads((ROOT / "schema/ths-0.1.schema.json").read_text(encoding="utf-8"))
    fixture = json.loads(
        (ROOT / "schema/examples/synthetic-demo-house.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(fixture)
    assert fixture["fixture"]["synthetic"] is True
    assert "synthetic" in fixture["dwelling"]["name"].lower()
    timezone_name = fixture["policies"]["quietHours"]["timezone"]
    assert ZoneInfo(timezone_name).key == timezone_name
    assert timezone_name == SEED_FILE.policies.timezone


def test_public_fixture_schema_requires_timezone_and_valid_clock_values():
    schema = json.loads((ROOT / "schema/ths-0.1.schema.json").read_text(encoding="utf-8"))
    fixture = json.loads(
        (ROOT / "schema/examples/synthetic-demo-house.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)

    missing_timezone = deepcopy(fixture)
    del missing_timezone["policies"]["quietHours"]["timezone"]
    invalid_clock = deepcopy(fixture)
    invalid_clock["policies"]["quietHours"]["start"] = "24:00"

    assert list(validator.iter_errors(missing_timezone))
    assert list(validator.iter_errors(invalid_clock))
