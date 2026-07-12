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
