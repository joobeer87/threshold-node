"""The public demo fixture must be valid and unambiguously synthetic."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def test_public_fixture_validates_and_is_synthetic():
    schema = json.loads((ROOT / "schema/ths-0.1.schema.json").read_text(encoding="utf-8"))
    fixture = json.loads(
        (ROOT / "schema/examples/synthetic-demo-house.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(fixture)
    assert fixture["fixture"]["synthetic"] is True
    assert "synthetic" in fixture["dwelling"]["name"].lower()
