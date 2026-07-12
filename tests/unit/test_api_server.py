"""ASGI-level tests for the authenticated, fail-closed API boundary."""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from threshold.api import server
from threshold.capture.seed import SEED_GRANTS
from threshold.core.auth import token_digest
from threshold.core.config import Settings
from threshold.core.ledger import JsonlLedger
from threshold.core.types import EventType, Grant, GrantStatus, Scope
from threshold.grants.manager import GrantManager


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
        demo_mode=True,
    )
    manager = GrantManager(server.FILE)
    for source in SEED_GRANTS:
        seeded = copy.deepcopy(source)
        if seeded.id == "g-neo":
            seeded.credential_digest = token_digest(GRANT_VALUE)
        manager.grants[seeded.id] = seeded

    monkeypatch.setattr(server, "SETTINGS", settings)
    monkeypatch.setattr(server, "MGR", manager)
    monkeypatch.setattr(server, "LEDGER", JsonlLedger(settings.ledger_path))
    monkeypatch.setattr(server, "_now", lambda: NOW)
    monkeypatch.setattr(server, "_new_grant_id", lambda: "g-issued-test")


def test_health_and_aurora_signature_remain_truthful():
    health = request("GET", "/health")
    assert health.status_code == 200
    assert health.json()["armed"] is False
    assert health.json()["interlock"] == "not_implemented"
    assert health.json()["ledger"] == "persistent_jsonl_configured"
    assert health.json()["ledger_availability"] == "not_probed"
    assert health.json()["adapters"] == []

    signature = request("GET", "/.well-known/aurora")
    assert signature.status_code == 200
    assert signature.json()["principle"] == "authority_before_autonomy"
    assert signature.json()["safety_receipt"]["secret_material_returned"] is False


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
    assert [entry["type"] for entry in server.LEDGER.read()] == [EventType.GRANT.value]


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
    assert server.LEDGER.read() == []


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
    server.MGR.grants[expiring.id] = expiring
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
    assert expiring.status == GrantStatus.EXPIRED

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
    server.MGR.grants[windowed.id] = windowed
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
    suspended = server.MGR.grants["g-neo"]
    suspended.status = GrantStatus.SUSPENDED
    response = request(
        "POST",
        "/grants/g-neo/revoke",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert response.json()["grant"]["status"] == "revoked"
    assert suspended.status == GrantStatus.REVOKED


def test_suspended_revoke_rolls_back_when_ledger_write_fails(monkeypatch):
    class FailingLedger:
        def record_event(self, *_args, **_kwargs):
            raise OSError("synthetic write failure")

    suspended = server.MGR.grants["g-neo"]
    suspended.status = GrantStatus.SUSPENDED
    monkeypatch.setattr(server, "LEDGER", FailingLedger())
    response = request(
        "POST",
        "/grants/g-neo/revoke",
        headers={"X-Threshold-Owner-Token": OWNER_VALUE},
    )
    assert response.status_code == 503
    assert suspended.status == GrantStatus.SUSPENDED


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


def test_ledger_write_failure_prevents_disclosure_and_rolls_back_issue(monkeypatch):
    class FailingLedger:
        def record_event(self, *_args, **_kwargs):
            raise OSError("private path and payload must not escape")

        def read(self, _limit=100):
            return []

    monkeypatch.setattr(server, "LEDGER", FailingLedger())
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


def test_public_openapi_schema_has_no_credential_digest():
    schema = request("GET", "/openapi.json")
    assert schema.status_code == 200
    document = schema.json()
    serialized = json.dumps(document, sort_keys=True)
    assert "credential_digest" not in serialized
    assert "/grants" in document["paths"]
    assert "/grants/{grant_id}/revoke" in document["paths"]

    for path, method, header in [
        ("/housefile", "get", "X-Threshold-Grant-Token"),
        ("/ledger", "get", "X-Threshold-Owner-Token"),
        ("/grants", "post", "X-Threshold-New-Grant-Token"),
    ]:
        parameter = next(
            item
            for item in document["paths"][path][method]["parameters"]
            if item["name"] == header
        )
        assert '"format": "password"' in json.dumps(parameter, sort_keys=True)
