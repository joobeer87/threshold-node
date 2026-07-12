"""THS-0005 — privacy-first, environment-backed configuration."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from hmac import compare_digest

from threshold.core.auth import is_valid_bearer_token
from threshold.core.errors import ConfigError


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class Settings:
    owner_token: str | None = field(repr=False)
    demo_grant_token: str | None = field(default=None, repr=False)
    bind: str = "127.0.0.1:8471"
    ledger_path: str = "data/ledger.jsonl"
    esp32_serial: str = "SIMULATED"
    demo_mode: bool = False
    allow_network_bind: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        token = values.get("THS_OWNER_TOKEN", "").strip() or None
        grant_token = values.get("THS_DEMO_GRANT_TOKEN", "").strip() or None
        return cls(
            owner_token=token,
            demo_grant_token=grant_token,
            bind=values.get("THS_BIND", "127.0.0.1:8471").strip(),
            ledger_path=(
                values.get("THS_LEDGER_PATH", "data/ledger.jsonl").strip()
                or "data/ledger.jsonl"
            ),
            esp32_serial=values.get("ESP32_SERIAL", "SIMULATED").strip(),
            demo_mode=_is_true(values.get("THS_DEMO_MODE")),
            allow_network_bind=_is_true(values.get("THS_ALLOW_NETWORK_BIND")),
        )

    def bind_address(self) -> tuple[str, int]:
        host, separator, raw_port = self.bind.rpartition(":")
        if not separator or not host or not raw_port.isdigit():
            raise ConfigError("THS_BIND must use host:port format")
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ConfigError("THS_BIND port must be between 1 and 65535")
        return host, port

    def validate_runtime(self) -> None:
        host, _ = self.bind_address()
        if not is_valid_bearer_token(self.owner_token):
            raise ConfigError(
                "THS_OWNER_TOKEN must be 32–512 visible ASCII characters"
            )
        if host not in {"127.0.0.1", "localhost", "::1"} and not self.allow_network_bind:
            raise ConfigError("non-loopback THS_BIND requires THS_ALLOW_NETWORK_BIND=true")
        if self.demo_mode and not is_valid_bearer_token(self.demo_grant_token):
            raise ConfigError(
                "THS_DEMO_GRANT_TOKEN must be 32–512 visible ASCII characters in demo mode"
            )
        if (
            self.demo_mode
            and self.owner_token is not None
            and self.demo_grant_token is not None
            and compare_digest(self.owner_token, self.demo_grant_token)
        ):
            raise ConfigError("owner and demo grant tokens must be different")

SETTINGS = Settings.from_env()
