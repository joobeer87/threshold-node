"""THS-0051 synthetic appliance flow with no device or household I/O."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from threshold.api import server
from threshold.core.config import Settings
from threshold.core.ledger import JsonlLedger
from threshold.core.types import GrantStatus
from threshold.grants.authority import GrantAuthority
from threshold.grants.store import GrantMetadataStore
from threshold.hardware.display import DisplayMode, DisplayState
from threshold.hardware.estop import InterlockState


OWNER_VALUE = "owner-synthetic-e2e-value-0000000001"
DEMO_VALUE = "demo-synthetic-e2e-value-00000000001"
GRANT_VALUE = "grant-synthetic-e2e-value-0000000001"
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)


def request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://threshold.synthetic",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


@pytest.fixture(autouse=True)
def synthetic_appliance(monkeypatch, tmp_path):
    settings = Settings(
        owner_token=OWNER_VALUE,
        demo_grant_token=DEMO_VALUE,
        ledger_path=str(tmp_path / "private" / "ledger.jsonl"),
        grant_store_path=str(tmp_path / "private" / "grants.json"),
        esp32_serial="SIMULATED",
        demo_mode=True,
    )
    ledger = JsonlLedger(settings.ledger_path)
    authority = GrantAuthority(
        server.FILE,
        GrantMetadataStore(settings.grant_store_path),
        ledger,
    )
    authority.ensure_ready(now=NOW)

    monkeypatch.setattr(server, "SETTINGS", settings)
    monkeypatch.setattr(server, "AUTHORITY", authority)
    monkeypatch.setattr(server, "MGR", authority.manager)
    monkeypatch.setattr(server, "LEDGER", ledger)
    monkeypatch.setattr(server, "ADAPTERS", ())
    monkeypatch.setattr(server, "DISPLAY_STATE", DisplayState())
    monkeypatch.setattr(server, "_now", lambda: NOW)
    monkeypatch.setattr(server, "_new_grant_id", lambda: "g-synthetic-e2e")
    monkeypatch.setattr(server, "INTERLOCK", server._build_simulated_interlock())


def test_grant_read_no_go_trip_and_suspended_denial_survive_rearm_and_restart():
    owner_headers = {
        "X-Threshold-Owner-Token": OWNER_VALUE,
        "X-Threshold-New-Grant-Token": GRANT_VALUE,
    }
    grant_headers = {"X-Threshold-Grant-Token": GRANT_VALUE}

    issued = request(
        "POST",
        "/grants",
        headers=owner_headers,
        json={
            "name": "Synthetic Appliance Agent",
            "kind": "agent",
            "scopes": ["read:layout", "command:navigate"],
            "zones": ["kitchen"],
        },
    )
    scoped_read = request(
        "GET",
        "/housefile",
        params={"grant": "g-synthetic-e2e"},
        headers=grant_headers,
    )
    no_go = request(
        "POST",
        "/command",
        headers=grant_headers,
        json={
            "grant": "g-synthetic-e2e",
            "verb": "navigate",
            "zone": "workshop",
        },
    )
    tripped = request(
        "POST",
        "/sim/interlock/trip",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    suspended = request(
        "GET",
        "/housefile",
        params={"grant": "g-synthetic-e2e"},
        headers=grant_headers,
    )

    assert issued.status_code == 201
    assert issued.json()["grant"]["id"] == "g-synthetic-e2e"
    assert scoped_read.status_code == 200
    assert scoped_read.json()["grant"]["id"] == "g-synthetic-e2e"
    assert no_go.status_code == 403
    assert no_go.json()["detail"] == {
        "policy_decision": "denied",
        "relayed": False,
        "reason": "gate_refused",
    }
    assert tripped.status_code == 200
    assert tripped.json()["state"] == "TRIPPED"
    assert tripped.json()["suspended_grants"] == 1
    assert tripped.json()["timing_scope"] == "simulated_software_path_only"
    assert tripped.json()["physical_stop_verified"] is False
    assert server.INTERLOCK.state == InterlockState.TRIPPED
    assert server.DISPLAY_STATE.frame(active_grants=0, now=NOW).mode == DisplayMode.TRIPPED
    assert suspended.status_code == 403
    assert suspended.json()["detail"]["reason"] == "grant_suspended"

    rearmed = request(
        "POST",
        "/sim/interlock/rearm",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    still_suspended = request(
        "GET",
        "/housefile",
        params={"grant": "g-synthetic-e2e"},
        headers=grant_headers,
    )
    assert rearmed.status_code == 200
    assert rearmed.json()["grants_restored"] is False
    assert still_suspended.status_code == 403
    assert still_suspended.json()["detail"]["reason"] == "grant_suspended"

    restarted = GrantAuthority(
        server.FILE,
        GrantMetadataStore(server.SETTINGS.grant_store_path),
        JsonlLedger(server.SETTINGS.ledger_path),
    )
    restarted.ensure_ready(now=NOW)
    assert restarted.grants["g-synthetic-e2e"].status == GrantStatus.SUSPENDED

    events = server.LEDGER.read()
    event_types = [event["type"] for event in events]
    assert list(reversed(event_types))[:4] == ["GRANT", "READ", "DENY", "ESTOP"]
    serialized_runtime = json.dumps(events, sort_keys=True) + Path(
        server.SETTINGS.grant_store_path
    ).read_text(encoding="utf-8")
    assert OWNER_VALUE not in serialized_runtime
    assert GRANT_VALUE not in serialized_runtime
    assert DEMO_VALUE not in serialized_runtime
