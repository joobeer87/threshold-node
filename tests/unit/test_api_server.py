"""ASGI-level tests for the authenticated, fail-closed API boundary."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from threshold.api import server
from threshold.capture.seed import SEED_GRANTS
from threshold.core.auth import token_digest
from threshold.core.config import Settings
from threshold.core.ledger import JsonlLedger
from threshold.core.types import EventType, Grant, GrantStatus, Scope
from threshold.grants.authority import GrantAuthority
from threshold.grants.store import GrantMetadataStore
from threshold.hardware.display import DisplayMode, DisplayState
from threshold.hardware.estop import InterlockState


OWNER_VALUE = "owner-local-test-value-000000000001"
GRANT_VALUE = "grant-local-test-value-000000000001"
NEW_GRANT_VALUE = "new-grant-local-test-value-000000001"
NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://threshold.test",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def issue_payload(**changes) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Synthetic Issued Agent",
        "kind": "agent",
        "scopes": ["read:layout", "command:navigate"],
        "zones": ["kitchen"],
        "window": "standing",
        "expires": "revocable",
    }
    payload.update(changes)
    return payload


def owner_headers(*, credential: str = NEW_GRANT_VALUE) -> dict[str, str]:
    return {
        "X-Threshold-Owner-Token": OWNER_VALUE,
        "X-Threshold-New-Grant-Token": credential,
    }


@pytest.fixture(autouse=True)
def configured_server(monkeypatch, tmp_path):
    settings = Settings(
        owner_token=OWNER_VALUE,
        demo_grant_token=GRANT_VALUE,
        ledger_path=str(tmp_path / "private" / "ledger.jsonl"),
        grant_store_path=str(tmp_path / "private" / "grants.json"),
        demo_mode=True,
    )
    seeded = copy.deepcopy(next(item for item in SEED_GRANTS if item.id == "g-neo"))
    seeded.credential_digest = token_digest(GRANT_VALUE)
    ledger = JsonlLedger(settings.ledger_path)
    authority = GrantAuthority(
        server.FILE,
        GrantMetadataStore(settings.grant_store_path),
        ledger,
        demo_mode=True,
        demo_seeds=(seeded,),
    )
    authority.ensure_ready(now=NOW)

    monkeypatch.setattr(server, "SETTINGS", settings)
    monkeypatch.setattr(server, "AUTHORITY", authority)
    monkeypatch.setattr(server, "MGR", authority.manager)
    monkeypatch.setattr(server, "LEDGER", ledger)
    monkeypatch.setattr(server, "_now", lambda: NOW)
    monkeypatch.setattr(server, "_new_grant_id", lambda: "g-issued-test")
    monkeypatch.setattr(server, "ADAPTERS", ())
    monkeypatch.setattr(server, "DISPLAY_STATE", DisplayState())
    monkeypatch.setattr(server, "INTERLOCK", server._build_simulated_interlock())


def persist_grant(grant: Grant, *, issued_at: datetime) -> Grant:
    grant.issued = timestamp(issued_at)
    return server.AUTHORITY.issue(grant, now=issued_at)


def test_health_and_aurora_signature_remain_truthful():
    health = request("GET", "/health")
    assert health.status_code == 200
    assert health.json()["armed"] is False
    assert health.json()["interlock"] == "simulated_latched"
    assert health.json()["interlock_state"] == "ARMED"
    assert health.json()["physical_stop_verified"] is False
    assert health.json()["timing_scope"] == "simulated_software_path_only"
    assert health.json()["ledger"] == "persistent_jsonl_configured"
    assert health.json()["ledger_availability"] == "not_probed"
    assert health.json()["adapters"] == []

    signature = request("GET", "/.well-known/aurora")
    assert signature.status_code == 200
    assert signature.json()["principle"] == "authority_before_autonomy"
    assert signature.json()["safety_receipt"]["secret_material_returned"] is False


def test_owner_snapshot_is_authenticated_canonical_and_credential_free():
    owner = {"X-Threshold-Owner-Token": OWNER_VALUE}
    assert request("GET", "/owner/snapshot").status_code == 401

    response = request(
        "GET",
        "/owner/snapshot",
        params={"ledger_limit": 1},
        headers=owner,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["housefile"]["schema"] == "ths/0.1"
    assert body["housefile"]["rev"] == "A"
    assert body["housefile"]["dwelling"] == {
        "name": "Threshold Demo House (Synthetic)"
    }
    assert body["housefile"]["zones"][0] == {
        "id": "kitchen",
        "name": "Kitchen",
        "access": "open",
        "boundary": [0.0, 0.0, 150.0, 100.0],
        "note": "",
        "outdoor": False,
    }
    assert body["housefile"]["policies"]["quietHours"] == {
        "start": "21:30",
        "end": "06:30",
        "timezone": "Etc/UTC",
    }
    assert body["grants"] == [
        {
            "id": "g-neo",
            "name": "NEO Unit 04",
            "kind": "humanoid",
            "scopes": [
                "read:layout",
                "read:inventory",
                "command:navigate",
                "command:manipulate",
            ],
            "zones": ["kitchen", "living", "office", "utility"],
            "window": "standing",
            "expires": "revocable",
            "status": "active",
            "issued": "2026-07-13T09:12:00Z",
        }
    ]
    assert body["status"]["health"] == request("GET", "/health").json()
    assert body["status"]["display"] == {"state": "ARMED"}
    assert body["status"]["active_grants"] == 1
    assert len(body["ledger"]) == 1
    assert set(body["ledger"][0]).issubset(
        {"ts", "type", "agent", "detail", "tier"}
    )

    serialized = json.dumps(body, sort_keys=True)
    assert OWNER_VALUE not in serialized
    assert GRANT_VALUE not in serialized
    assert token_digest(GRANT_VALUE) not in serialized
    assert "credential" not in serialized
    assert "transaction" not in serialized
    assert "grant_revision" not in serialized


def test_owner_status_tracks_simulated_trip_without_restoring_credentials():
    owner = {"X-Threshold-Owner-Token": OWNER_VALUE}
    initial = request("GET", "/owner/status", headers=owner)
    assert initial.status_code == 200
    assert initial.json()["health"]["interlock_state"] == "ARMED"
    assert initial.json()["display"] == {"state": "ARMED"}
    assert initial.json()["active_grants"] == 1

    assert request("POST", "/sim/interlock/trip", headers=owner).status_code == 200
    tripped = request("GET", "/owner/status", headers=owner)

    assert tripped.status_code == 200
    assert tripped.json()["health"]["interlock_state"] == "TRIPPED"
    assert tripped.json()["display"] == {"state": "TRIPPED"}
    assert tripped.json()["active_grants"] == 0


@pytest.mark.parametrize("ledger_limit", [0, 1001])
def test_owner_snapshot_ledger_limit_is_bounded(ledger_limit):
    response = request(
        "GET",
        "/owner/snapshot",
        params={"ledger_limit": ledger_limit},
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "request validation failed"}


def test_owner_snapshot_fails_closed_when_ledger_is_unavailable(monkeypatch, tmp_path):
    unavailable = tmp_path / "ledger-directory"
    unavailable.mkdir()
    monkeypatch.setattr(server, "LEDGER", JsonlLedger(unavailable))

    response = request(
        "GET",
        "/owner/snapshot",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "audit ledger unavailable"}
    assert "housefile" not in response.text
    assert str(unavailable) not in response.text


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "*",
        "http://localhost:5173",
        "http://127.0.0.1.evil.test:5173",
        "https://127.0.0.1:5173",
    ],
)
def test_owner_routes_reject_non_exact_origins(origin):
    response = request(
        "GET",
        "/owner/snapshot",
        headers={
            "Origin": origin,
            "X-Threshold-Owner-Token": OWNER_VALUE,
        },
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "owner origin not allowed"}
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/owner/status"),
        ("GET", "/ledger"),
        ("POST", "/grants"),
        ("POST", "/grants/g-neo/revoke"),
        ("POST", "/sim/interlock/trip"),
        ("POST", "/sim/interlock/rearm"),
    ],
)
def test_every_owner_route_rejects_a_foreign_origin_before_processing(method, path):
    response = request(
        method,
        path,
        headers={
            "Origin": "https://synthetic-untrusted.example",
            "X-Threshold-Owner-Token": OWNER_VALUE,
        },
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "owner origin not allowed"}


@pytest.mark.parametrize(
    "origin",
    ["http://threshold.test", "http://127.0.0.1:5173"],
)
def test_owner_routes_allow_only_same_or_fixed_console_origin(origin):
    response = request(
        "GET",
        "/owner/status",
        headers={
            "Origin": origin,
            "X-Threshold-Owner-Token": OWNER_VALUE,
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "*" not in json.dumps(dict(response.headers))


def test_owner_console_preflight_is_exact_and_header_bounded():
    origin = "http://127.0.0.1:5173"
    allowed = request(
        "OPTIONS",
        "/owner/snapshot",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Threshold-Owner-Token",
        },
    )
    forbidden = request(
        "OPTIONS",
        "/owner/snapshot",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert allowed.status_code == 204
    assert allowed.headers["access-control-allow-origin"] == origin
    assert allowed.headers["access-control-allow-methods"] == "GET"
    assert "*" not in json.dumps(dict(allowed.headers))
    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "owner headers not allowed"}


def test_foreign_origin_does_not_change_public_health_access():
    response = request(
        "GET",
        "/health",
        headers={"Origin": "https://synthetic-untrusted.example"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_owner_and_grant_auth_boundaries_are_separate():
    payload = issue_payload()
    no_owner = request(
        "POST",
        "/grants",
        headers={"X-Threshold-New-Grant-Token": NEW_GRANT_VALUE},
        json=payload,
    )
    wrong_owner = request(
        "POST",
        "/grants",
        headers={
            "X-Threshold-Owner-Token": GRANT_VALUE,
            "X-Threshold-New-Grant-Token": NEW_GRANT_VALUE,
        },
        json=payload,
    )
    assert no_owner.status_code == 401
    assert wrong_owner.status_code == 401

    assert request("GET", "/housefile", params={"grant": "g-neo"}).status_code == 401
    assert request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers={"X-Threshold-Grant-Token": OWNER_VALUE},
    ).status_code == 401


def test_api_fails_closed_if_owner_and_demo_credentials_match(monkeypatch):
    shared = "synthetic-shared-token-value-000000001"
    monkeypatch.setattr(
        server,
        "SETTINGS",
        Settings(
            owner_token=shared,
            demo_grant_token=shared,
            demo_mode=True,
            ledger_path=server.SETTINGS.ledger_path,
        ),
    )
    response = request(
        "GET",
        "/ledger",
        headers={"X-Threshold-Owner-Token": shared},
    )
    assert response.status_code == 503
    assert shared not in response.text


def test_issue_registers_only_a_digest_and_returns_a_safe_projection():
    response = request(
        "POST",
        "/grants",
        headers=owner_headers(),
        json=issue_payload(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["credential_registered"] is True
    assert body["grant"] == {
        "id": "g-issued-test",
        "name": "Synthetic Issued Agent",
        "kind": "agent",
        "scopes": ["read:layout", "command:navigate"],
        "zones": ["kitchen"],
        "window": "standing",
        "expires": "revocable",
        "status": "active",
        "issued": "2026-07-15T12:00:00Z",
    }

    serialized = json.dumps(body, sort_keys=True)
    assert NEW_GRANT_VALUE not in serialized
    assert "credential_digest" not in serialized
    stored = server.MGR.grants["g-issued-test"]
    assert stored.credential_digest == token_digest(NEW_GRANT_VALUE)
    assert NEW_GRANT_VALUE not in repr(stored)
    assert stored.credential_digest not in repr(stored)
    assert [entry["type"] for entry in server.LEDGER.read()].count(
        EventType.GRANT.value
    ) == 1


def test_issued_credential_authenticates_only_its_grant():
    assert request(
        "POST",
        "/grants",
        headers=owner_headers(),
        json=issue_payload(),
    ).status_code == 201

    issued_read = request(
        "GET",
        "/housefile",
        params={"grant": "g-issued-test"},
        headers={"X-Threshold-Grant-Token": NEW_GRANT_VALUE},
    )
    wrong_grant = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers={"X-Threshold-Grant-Token": NEW_GRANT_VALUE},
    )
    assert issued_read.status_code == 200
    assert issued_read.json()["grant"]["id"] == "g-issued-test"
    assert wrong_grant.status_code == 401


def test_duplicate_and_owner_credentials_are_rejected_without_a_grant_event():
    first = request(
        "POST",
        "/grants",
        headers=owner_headers(),
        json=issue_payload(),
    )
    duplicate = request(
        "POST",
        "/grants",
        headers=owner_headers(),
        json=issue_payload(name="Another Synthetic Agent"),
    )
    owner_reuse = request(
        "POST",
        "/grants",
        headers=owner_headers(credential=OWNER_VALUE),
        json=issue_payload(name="Owner Reuse"),
    )
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert owner_reuse.status_code == 422
    assert [entry["type"] for entry in server.LEDGER.read()].count("GRANT") == 1


@pytest.mark.parametrize(
    "payload",
    [
        issue_payload(scopes=[]),
        issue_payload(zones=[]),
        issue_payload(zones=["workshop"]),
        issue_payload(zones=["unknown-zone"]),
        issue_payload(kind="vehicle"),
        issue_payload(scopes=["unknown:scope"]),
        issue_payload(extra="not accepted"),
        issue_payload(window="sometime later"),
        issue_payload(expires="2026-07-15T12:00:00Z"),
        issue_payload(expires="2026-07-16T12:00:00"),
    ],
)
def test_invalid_grants_fail_with_422_and_are_not_stored(payload):
    response = request("POST", "/grants", headers=owner_headers(), json=payload)
    assert response.status_code == 422
    assert "g-issued-test" not in server.MGR.grants
    assert [entry["type"] for entry in server.LEDGER.read()] == [
        EventType.PROVISION.value
    ]


def test_semantic_grant_errors_do_not_reflect_zone_values():
    private_sentinel = "synthetic-private-zone-sentinel-000000001"
    response = request(
        "POST",
        "/grants",
        headers=owner_headers(),
        json=issue_payload(zones=[private_sentinel]),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "grant policy is invalid"}
    assert private_sentinel not in response.text


def test_short_new_credential_is_rejected_by_the_route_schema():
    short_credential = "synthetic-short"
    response = request(
        "POST",
        "/grants",
        headers=owner_headers(credential=short_credential),
        json=issue_payload(),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "grant credential format is invalid"}
    assert short_credential not in response.text
    assert "g-issued-test" not in server.MGR.grants


def test_oversized_new_credential_is_rejected_without_reflection():
    invalid_credential = "x" * 513
    response = request(
        "POST",
        "/grants",
        headers=owner_headers(credential=invalid_credential),
        json=issue_payload(),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "grant credential format is invalid"}
    assert invalid_credential not in response.text


def test_schema_errors_do_not_reflect_unexpected_body_values():
    private_sentinel = "synthetic-private-sentinel-000000000001"
    response = request(
        "POST",
        "/grants",
        headers=owner_headers(),
        json=issue_payload(credential_digest=private_sentinel),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "request validation failed"}
    assert private_sentinel not in response.text


def test_expiry_is_enforced_on_housefile_and_command_at_the_exact_boundary(monkeypatch):
    expiring = Grant(
        "g-expiring-test",
        "Synthetic Expiring Agent",
        "agent",
        (Scope.READ_LAYOUT, Scope.CMD_NAVIGATE),
        ("kitchen",),
        expires=timestamp(NOW),
        credential_digest=token_digest(NEW_GRANT_VALUE),
    )
    expiring = persist_grant(expiring, issued_at=NOW - timedelta(hours=1))
    headers = {"X-Threshold-Grant-Token": NEW_GRANT_VALUE}

    monkeypatch.setattr(server, "_now", lambda: NOW - timedelta(microseconds=1))
    assert request(
        "GET", "/housefile", params={"grant": expiring.id}, headers=headers
    ).status_code == 200

    monkeypatch.setattr(server, "_now", lambda: NOW)
    expired_read = request(
        "GET", "/housefile", params={"grant": expiring.id}, headers=headers
    )
    assert expired_read.status_code == 403
    assert expired_read.json()["detail"]["reason"] == "grant_expired"
    assert server.AUTHORITY.grants[expiring.id].status == GrantStatus.EXPIRED

    expired_command = request(
        "POST",
        "/command",
        headers=headers,
        json={"grant": expiring.id, "verb": "navigate", "zone": "kitchen"},
    )
    assert expired_command.status_code == 403
    assert expired_command.json()["detail"]["reason"] == "grant_expired"


def test_one_time_window_is_enforced_by_the_api(monkeypatch):
    start = NOW + timedelta(hours=1)
    end = NOW + timedelta(hours=2)
    windowed = Grant(
        "g-window-test",
        "Synthetic Windowed Agent",
        "agent",
        (Scope.READ_LAYOUT,),
        ("kitchen",),
        window=f"{timestamp(start)}/{timestamp(end)}",
        credential_digest=token_digest(NEW_GRANT_VALUE),
    )
    windowed = persist_grant(windowed, issued_at=NOW - timedelta(hours=1))
    headers = {"X-Threshold-Grant-Token": NEW_GRANT_VALUE}

    before = request(
        "GET", "/housefile", params={"grant": windowed.id}, headers=headers
    )
    assert before.status_code == 403
    assert before.json()["detail"]["reason"] == "grant_outside_window"

    monkeypatch.setattr(server, "_now", lambda: start)
    assert request(
        "GET", "/housefile", params={"grant": windowed.id}, headers=headers
    ).status_code == 200

    monkeypatch.setattr(server, "_now", lambda: end)
    ended = request(
        "GET", "/housefile", params={"grant": windowed.id}, headers=headers
    )
    assert ended.status_code == 403
    assert ended.json()["detail"]["reason"] == "grant_expired"


def test_command_contract_distinguishes_policy_allowance_from_relay():
    headers = {"X-Threshold-Grant-Token": GRANT_VALUE}
    allowed = request(
        "POST",
        "/command",
        headers=headers,
        json={"grant": "g-neo", "verb": "navigate", "zone": "kitchen"},
    )
    denied = request(
        "POST",
        "/command",
        headers=headers,
        json={"grant": "g-neo", "verb": "navigate", "zone": "workshop"},
    )
    assert allowed.status_code == 503
    assert allowed.json()["detail"] == {
        "policy_decision": "allowed",
        "relayed": False,
        "reason": "adapter_not_configured",
        "tier": "UNAVAILABLE",
    }
    assert denied.status_code == 403
    assert denied.json()["detail"] == {
        "policy_decision": "denied",
        "relayed": False,
        "reason": "gate_refused",
    }


def test_active_quiet_hours_durably_deny_commands_only(monkeypatch):
    monkeypatch.setattr(
        server,
        "FILE",
        replace(
            server.FILE,
            policies=replace(
                server.FILE.policies,
                quiet_start="11:30",
                quiet_end="12:30",
                timezone="Etc/UTC",
            ),
        ),
    )
    headers = {"X-Threshold-Grant-Token": GRANT_VALUE}

    read = request("GET", "/housefile", params={"grant": "g-neo"}, headers=headers)
    denied = request(
        "POST",
        "/command",
        headers=headers,
        json={"grant": "g-neo", "verb": "navigate", "zone": "kitchen"},
    )

    assert read.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["detail"] == {
        "policy_decision": "denied",
        "relayed": False,
        "reason": "quiet_hours_active",
    }
    assert server.LEDGER.read()[0]["detail"] == (
        "command refused: quiet_hours_active"
    )


@pytest.mark.parametrize(
    ("request_now", "expected_status", "expected_reason"),
    [
        (
            datetime(2026, 11, 1, 5, 29, tzinfo=timezone.utc),
            503,
            "adapter_not_configured",
        ),
        (
            datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc),
            403,
            "quiet_hours_active",
        ),
        (
            datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc),
            403,
            "quiet_hours_active",
        ),
        (
            datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc),
            503,
            "adapter_not_configured",
        ),
    ],
)
def test_quiet_hours_use_iana_zoneinfo_across_dst_fold(
    monkeypatch,
    request_now,
    expected_status,
    expected_reason,
):
    monkeypatch.setattr(server, "_now", lambda: request_now)
    monkeypatch.setattr(
        server,
        "FILE",
        replace(
            server.FILE,
            policies=replace(
                server.FILE.policies,
                quiet_start="01:30",
                quiet_end="02:30",
                timezone="America/Toronto",
            ),
        ),
    )

    response = request(
        "POST",
        "/command",
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
        json={"grant": "g-neo", "verb": "navigate", "zone": "kitchen"},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["reason"] == expected_reason


@pytest.mark.parametrize(
    ("timezone_name", "quiet_start", "reason"),
    [
        ("Synthetic/Not-A-Timezone", "21:30", "quiet_hours_timezone_invalid"),
        ("Etc/UTC", "25:00", "quiet_hours_invalid"),
    ],
)
def test_invalid_quiet_hours_fail_commands_closed_but_not_reads(
    monkeypatch,
    timezone_name,
    quiet_start,
    reason,
):
    monkeypatch.setattr(
        server,
        "FILE",
        replace(
            server.FILE,
            policies=replace(
                server.FILE.policies,
                quiet_start=quiet_start,
                timezone=timezone_name,
            ),
        ),
    )
    headers = {"X-Threshold-Grant-Token": GRANT_VALUE}

    read = request("GET", "/housefile", params={"grant": "g-neo"}, headers=headers)
    command = request(
        "POST",
        "/command",
        headers=headers,
        json={"grant": "g-neo", "verb": "navigate", "zone": "kitchen"},
    )

    assert read.status_code == 200
    assert command.status_code == 503
    assert command.json()["detail"] == {
        "policy_decision": "denied",
        "relayed": False,
        "reason": reason,
    }
    assert server.LEDGER.read()[0]["detail"] == f"command refused: {reason}"


def test_quiet_hours_deny_is_not_returned_until_the_receipt_is_durable(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "FILE",
        replace(
            server.FILE,
            policies=replace(
                server.FILE.policies,
                quiet_start="11:30",
                quiet_end="12:30",
                timezone="Etc/UTC",
            ),
        ),
    )

    def fail_record(*_args, **_kwargs):
        raise OSError("synthetic durable deny failure")

    monkeypatch.setattr(server.LEDGER, "record_event", fail_record)
    response = request(
        "POST",
        "/command",
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
        json={"grant": "g-neo", "verb": "navigate", "zone": "kitchen"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "audit ledger unavailable"}
    assert "synthetic durable deny failure" not in response.text


def test_command_captures_utc_once_for_policy_and_receipt(monkeypatch):
    calls = 0

    def counted_now():
        nonlocal calls
        calls += 1
        return NOW

    monkeypatch.setattr(server, "_now", counted_now)
    response = request(
        "POST",
        "/command",
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
        json={"grant": "g-neo", "verb": "navigate", "zone": "kitchen"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "adapter_not_configured"
    assert calls == 1
    assert server.LEDGER.read()[0]["ts"] == timestamp(NOW)


def test_command_parameters_are_denied_until_verb_schemas_exist():
    response = request(
        "POST",
        "/command",
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
        json={
            "grant": "g-neo",
            "verb": "navigate",
            "zone": "kitchen",
            "params": {"speed": "fast"},
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == {
        "policy_decision": "denied",
        "relayed": False,
        "reason": "unsupported_params",
    }


def test_revoke_is_owner_authenticated_idempotent_and_durably_logged_once():
    assert request(
        "POST", "/grants", headers=owner_headers(), json=issue_payload()
    ).status_code == 201
    path = "/grants/g-issued-test/revoke"
    unauthorized = request("POST", path)
    first = request(
        "POST", path, headers={"X-Threshold-Owner-Token": OWNER_VALUE}
    )
    repeated = request(
        "POST", path, headers={"X-Threshold-Owner-Token": OWNER_VALUE}
    )
    missing = request(
        "POST",
        "/grants/g-missing/revoke",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert unauthorized.status_code == 401
    assert first.status_code == 200 and first.json()["changed"] is True
    assert first.json()["grant"]["status"] == "revoked"
    assert repeated.status_code == 200 and repeated.json()["changed"] is False
    assert missing.status_code == 404
    assert [entry["type"] for entry in server.LEDGER.read()].count("REVOKE") == 1


def test_suspended_grant_can_be_explicitly_revoked():
    assert server.AUTHORITY.suspend_all(now=NOW) == 1
    response = request(
        "POST",
        "/grants/g-neo/revoke",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert response.json()["grant"]["status"] == "revoked"
    assert server.AUTHORITY.grants["g-neo"].status == GrantStatus.REVOKED


def test_suspended_revoke_remains_restrictive_when_ledger_write_fails(monkeypatch):
    assert server.AUTHORITY.suspend_all(now=NOW) == 1

    def fail_append(_prepared):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(server.AUTHORITY.ledger, "append_prepared", fail_append)
    response = request(
        "POST",
        "/grants/g-neo/revoke",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert response.status_code == 503
    reloaded = GrantMetadataStore(server.SETTINGS.grant_store_path).load()
    assert reloaded["g-neo"].status == GrantStatus.REVOKED


def test_owner_can_read_bounded_persisted_events_without_credentials():
    read = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
    )
    assert read.status_code == 200
    unauthorized = request("GET", "/ledger")
    response = request(
        "GET",
        "/ledger",
        params={"limit": 1},
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert len(response.json()) == 1
    serialized = json.dumps(response.json())
    assert GRANT_VALUE not in serialized
    assert OWNER_VALUE not in serialized


def test_owner_ledger_read_surfaces_storage_unavailability(monkeypatch, tmp_path):
    unavailable = tmp_path / "ledger-directory"
    unavailable.mkdir()
    monkeypatch.setattr(server, "LEDGER", JsonlLedger(unavailable))
    response = request(
        "GET",
        "/ledger",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "audit ledger unavailable"}
    assert str(unavailable) not in response.text


def test_policy_clock_is_captured_inside_the_grant_lock(monkeypatch):
    class ObservedLock:
        entered = False

        def __enter__(self):
            self.entered = True

        def __exit__(self, *_args):
            self.entered = False

    observed = ObservedLock()

    def guarded_now():
        assert observed.entered is True
        return NOW

    monkeypatch.setattr(server, "GRANT_LOCK", observed)
    monkeypatch.setattr(server, "_now", guarded_now)
    response = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
    )
    assert response.status_code == 200


def test_ledger_write_failure_prevents_disclosure_and_aborts_pending_issue(monkeypatch):
    class FailingLedger:
        def record_event(self, *_args, **_kwargs):
            raise OSError("private path and payload must not escape")

        def read(self, _limit=100):
            return []

    monkeypatch.setattr(server, "LEDGER", FailingLedger())

    def fail_prepared(_prepared):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(server.AUTHORITY.ledger, "append_prepared", fail_prepared)
    read = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
    )
    issue = request(
        "POST", "/grants", headers=owner_headers(), json=issue_payload()
    )
    assert read.status_code == 503
    assert read.json()["detail"] == "audit ledger unavailable"
    assert issue.status_code == 503
    assert "g-issued-test" not in server.MGR.grants
    assert "private path" not in read.text + issue.text


def test_simulated_trip_is_owner_authenticated_durable_and_idempotent():
    unauthorized = request("POST", "/sim/interlock/trip")
    assert unauthorized.status_code == 401

    headers = {"X-Threshold-Owner-Token": OWNER_VALUE}
    first = request("POST", "/sim/interlock/trip", headers=headers)
    repeated = request("POST", "/sim/interlock/trip", headers=headers)

    assert first.status_code == 200
    assert first.json()["state"] == "TRIPPED"
    assert first.json()["newly_tripped"] is True
    assert first.json()["persistence_succeeded"] is True
    assert first.json()["suspended_grants"] == 1
    assert first.json()["adapter_call_attempts"] == 0
    assert first.json()["adapter_call_completions"] == 0
    assert first.json()["adapter_call_failures"] == 0
    assert first.json()["simulated_display_updated"] is True
    assert first.json()["synthetic_receipt_rendered"] is True
    assert first.json()["timing_scope"] == "simulated_software_path_only"
    assert first.json()["physical_stop_verified"] is False
    assert repeated.status_code == 200
    assert repeated.json()["newly_tripped"] is False
    assert repeated.json()["suspended_grants"] == 1
    assert server.AUTHORITY.grants["g-neo"].status == GrantStatus.SUSPENDED
    assert server.INTERLOCK.state == InterlockState.TRIPPED
    assert server.DISPLAY_STATE.frame(active_grants=0, now=NOW).mode == DisplayMode.TRIPPED
    assert [event["type"] for event in server.LEDGER.read()].count("ESTOP") == 1

    health = request("GET", "/health")
    assert health.json()["armed"] is False
    assert health.json()["interlock_state"] == "TRIPPED"


def test_simulated_zero_grant_trip_still_commits_estop():
    server.AUTHORITY.revoke("g-neo", now=NOW)

    response = request(
        "POST",
        "/sim/interlock/trip",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )

    assert response.status_code == 200
    assert response.json()["suspended_grants"] == 0
    assert response.json()["persistence_succeeded"] is True
    assert [event["type"] for event in server.LEDGER.read()].count("ESTOP") == 1


def test_rearm_clears_only_the_local_latch_and_never_restores_grants():
    headers = {"X-Threshold-Owner-Token": OWNER_VALUE}
    assert request("POST", "/sim/interlock/trip", headers=headers).status_code == 200

    response = request("POST", "/sim/interlock/rearm", headers=headers)
    read = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
    )

    assert response.status_code == 200
    assert response.json() == {
        "state": "ARMED",
        "changed": True,
        "grants_restored": False,
        "timing_scope": "simulated_software_path_only",
        "physical_stop_verified": False,
    }
    assert server.INTERLOCK.state == InterlockState.ARMED
    assert server.AUTHORITY.grants["g-neo"].status == GrantStatus.SUSPENDED
    assert read.status_code == 403
    assert read.json()["detail"]["reason"] == "grant_suspended"


@pytest.mark.parametrize(
    "settings",
    [
        Settings(
            owner_token=OWNER_VALUE,
            demo_grant_token=GRANT_VALUE,
            demo_mode=False,
            esp32_serial="SIMULATED",
        ),
        Settings(
            owner_token=OWNER_VALUE,
            demo_grant_token=GRANT_VALUE,
            demo_mode=True,
            esp32_serial="synthetic-device",
        ),
    ],
)
def test_simulated_routes_require_demo_mode_and_exact_simulated_serial(
    monkeypatch,
    settings,
):
    monkeypatch.setattr(server, "SETTINGS", settings)
    response = request(
        "POST",
        "/sim/interlock/trip",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "simulated appliance is not enabled"}
    assert server.INTERLOCK.state == InterlockState.ARMED


def test_failed_trip_stays_latched_denies_use_and_cannot_rearm(monkeypatch):
    private_sentinel = "synthetic-private-trip-failure"

    def fail_suspend(*, now):
        del now
        raise OSError(private_sentinel)

    monkeypatch.setattr(server.AUTHORITY, "suspend_all", fail_suspend)
    owner = {"X-Threshold-Owner-Token": OWNER_VALUE}
    trip = request("POST", "/sim/interlock/trip", headers=owner)
    read = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers={"X-Threshold-Grant-Token": GRANT_VALUE},
    )
    issue = request("POST", "/grants", headers=owner_headers(), json=issue_payload())
    rearm = request("POST", "/sim/interlock/rearm", headers=owner)

    assert trip.status_code == 503
    assert trip.json()["detail"]["state"] == "TRIPPED"
    assert read.status_code == 403
    assert read.json()["detail"]["reason"] == "interlock_tripped"
    assert issue.status_code == 423
    assert issue.json()["detail"]["reason"] == "interlock_tripped"
    assert rearm.status_code == 503
    assert rearm.json()["detail"]["grants_restored"] is False
    assert server.INTERLOCK.state == InterlockState.TRIPPED
    assert server.AUTHORITY.grants["g-neo"].status == GrantStatus.ACTIVE
    assert private_sentinel not in trip.text + read.text + issue.text + rearm.text


def test_durable_reads_and_denies_drive_simulated_display_transients():
    grant_headers = {"X-Threshold-Grant-Token": GRANT_VALUE}
    read = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers=grant_headers,
    )
    assert read.status_code == 200
    read_frame = server.DISPLAY_STATE.frame(active_grants=1, now=NOW)
    assert read_frame.mode == DisplayMode.READ
    assert read_frame.agent == "g-neo"

    denied = request(
        "POST",
        "/command",
        headers=grant_headers,
        json={"grant": "g-neo", "verb": "navigate", "zone": "workshop"},
    )
    assert denied.status_code == 403
    deny_frame = server.DISPLAY_STATE.frame(active_grants=1, now=NOW)
    assert deny_frame.mode == DisplayMode.DENY
    assert deny_frame.agent == "g-neo"


def test_display_failures_do_not_reverse_durable_policy_results(monkeypatch):
    class FailingDisplay:
        def on_read(self, *_args, **_kwargs):
            raise RuntimeError("synthetic private display read failure")

        def on_deny(self, *_args, **_kwargs):
            raise RuntimeError("synthetic private display deny failure")

        def trip(self):
            raise RuntimeError("synthetic private display trip failure")

        def rearm(self):
            raise RuntimeError("synthetic private display rearm failure")

    monkeypatch.setattr(server, "DISPLAY_STATE", FailingDisplay())
    grant_headers = {"X-Threshold-Grant-Token": GRANT_VALUE}

    read = request(
        "GET",
        "/housefile",
        params={"grant": "g-neo"},
        headers=grant_headers,
    )
    denied = request(
        "POST",
        "/command",
        headers=grant_headers,
        json={"grant": "g-neo", "verb": "navigate", "zone": "workshop"},
    )
    tripped = request(
        "POST",
        "/sim/interlock/trip",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    rearmed = request(
        "POST",
        "/sim/interlock/rearm",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )

    assert read.status_code == 200
    assert denied.status_code == 403
    assert tripped.status_code == 200
    assert tripped.json()["simulated_display_updated"] is False
    assert server.AUTHORITY.grants["g-neo"].status == GrantStatus.SUSPENDED
    assert rearmed.status_code == 200
    assert rearmed.json()["grants_restored"] is False


def test_public_openapi_schema_has_no_credential_digest():
    schema = request("GET", "/openapi.json")
    assert schema.status_code == 200
    document = schema.json()
    serialized = json.dumps(document, sort_keys=True)
    assert "credential_digest" not in serialized
    assert "/grants" in document["paths"]
    assert "/grants/{grant_id}/revoke" in document["paths"]
    assert "/sim/interlock/trip" in document["paths"]
    assert "/sim/interlock/rearm" in document["paths"]
    assert "/owner/snapshot" in document["paths"]
    assert "/owner/status" in document["paths"]

    for path, method, header in [
        ("/housefile", "get", "X-Threshold-Grant-Token"),
        ("/ledger", "get", "X-Threshold-Owner-Token"),
        ("/owner/snapshot", "get", "X-Threshold-Owner-Token"),
        ("/owner/status", "get", "X-Threshold-Owner-Token"),
        ("/grants", "post", "X-Threshold-New-Grant-Token"),
        ("/sim/interlock/trip", "post", "X-Threshold-Owner-Token"),
        ("/sim/interlock/rearm", "post", "X-Threshold-Owner-Token"),
    ]:
        parameter = next(
            item
            for item in document["paths"][path][method]["parameters"]
            if item["name"] == header
        )
        assert '"format": "password"' in json.dumps(parameter, sort_keys=True)
