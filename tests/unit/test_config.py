"""Privacy-first configuration behavior."""

import pytest

from threshold.core.config import Settings
from threshold.core.errors import ConfigError


OWNER_ENV = "THS_OWNER_" + "TOKEN"


def test_defaults_bind_to_loopback_without_credentials():
    settings = Settings.from_env({})
    assert settings.bind_address() == ("127.0.0.1", 8471)
    assert settings.owner_token is None
    assert settings.demo_grant_token is None
    assert settings.ledger_path == "data/ledger.jsonl"
    assert settings.grant_store_path == "data/grants.json"


def test_ledger_path_can_be_set_without_exposing_it_in_runtime_validation():
    settings = Settings.from_env({"THS_LEDGER_PATH": "data/synthetic-ledger.jsonl"})
    assert settings.ledger_path == "data/synthetic-ledger.jsonl"


def test_grant_store_path_can_be_configured():
    settings = Settings.from_env(
        {"THS_GRANT_STORE_PATH": "data/synthetic-grants.json"}
    )
    assert settings.grant_store_path == "data/synthetic-grants.json"


def test_runtime_rejects_missing_owner_token():
    with pytest.raises(ConfigError, match="THS_OWNER_TOKEN"):
        Settings.from_env({}).validate_runtime()


def test_runtime_rejects_implicit_network_bind():
    settings = Settings.from_env(
        {
            OWNER_ENV: "o" * 32,
            "THS_BIND": "0.0.0.0:8471",
        }
    )
    with pytest.raises(ConfigError, match="THS_ALLOW_NETWORK_BIND"):
        settings.validate_runtime()


def test_runtime_allows_explicit_network_bind():
    settings = Settings.from_env(
        {
            OWNER_ENV: "o" * 32,
            "THS_BIND": "0.0.0.0:8471",
            "THS_ALLOW_NETWORK_BIND": "true",
        }
    )
    settings.validate_runtime()


def test_demo_mode_requires_separate_grant_token():
    settings = Settings.from_env(
        {
            OWNER_ENV: "o" * 32,
            "THS_DEMO_MODE": "true",
        }
    )
    with pytest.raises(ConfigError, match="THS_DEMO_GRANT_TOKEN"):
        settings.validate_runtime()


@pytest.mark.parametrize("invalid", ["x" * 31, "x" * 32 + "é", "x" * 513])
def test_runtime_rejects_tokens_that_are_not_bounded_visible_ascii(invalid):
    settings = Settings.from_env({OWNER_ENV: invalid})
    with pytest.raises(ConfigError, match="THS_OWNER_TOKEN"):
        settings.validate_runtime()


def test_demo_owner_and_grant_tokens_must_be_different():
    shared = "synthetic-shared-token-value-000000001"
    settings = Settings.from_env(
        {
            OWNER_ENV: shared,
            "THS_DEMO_MODE": "true",
            "THS_DEMO_GRANT_TOKEN": shared,
        }
    )
    with pytest.raises(ConfigError, match="must be different"):
        settings.validate_runtime()


def test_settings_repr_never_contains_plaintext_tokens():
    owner = "synthetic-owner-token-value-000000001"
    grant = "synthetic-grant-token-value-000000001"
    settings = Settings(owner_token=owner, demo_grant_token=grant)
    rendered = repr(settings)
    assert owner not in rendered
    assert grant not in rendered
