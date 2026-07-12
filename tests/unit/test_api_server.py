"""API-boundary safety tests without a network client dependency."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from threshold.api import server
from threshold.core.auth import token_digest
from threshold.core.config import Settings
from threshold.core.types import Grant, GrantStatus, Scope


OWNER_VALUE = "owner-local-test-value-000000000001"
GRANT_VALUE = "grant-local-test-value-000000000001"


@pytest.fixture(autouse=True)
def configured_server(monkeypatch):
    settings = Settings(
        owner_token=OWNER_VALUE,
        demo_grant_token=GRANT_VALUE,
        demo_mode=True,
    )
    monkeypatch.setattr(server, "SETTINGS", settings)
    grant = server.MGR.grants["g-neo"]
    previous_digest = grant.credential_digest
    grant.credential_digest = token_digest(GRANT_VALUE)
    server.LEDGER.clear()
    yield
    grant.credential_digest = previous_digest
    server.LEDGER.clear()


def exception_status(callable_, *args, **kwargs) -> int:
    with pytest.raises(HTTPException) as caught:
        callable_(*args, **kwargs)
    return caught.value.status_code


def test_health_is_truthful_pre_alpha():
    payload = server.health()
    assert payload["armed"] is False
    assert payload["interlock"] == "not_implemented"
    assert payload["adapters"] == []


def test_aurora_easter_egg_is_public_safe_and_honest():
    payload = server.aurora_signature()
    assert payload["principle"] == "authority_before_autonomy"
    assert payload["boundary"]["fail_closed"] is True
    assert payload["safety_receipt"] == {
        "secret_material_returned": False,
        "unauthorized_action_executed": False,
        "private_control_plane_exposed": False,
    }
    assert "not embedded" in payload["disclosure"]
    route = next(route for route in server.app.routes if route.path == "/.well-known/aurora")
    assert route.include_in_schema is False


def test_grant_endpoint_fails_closed():
    assert exception_status(server.housefile, "g-neo", None) == 401
    assert exception_status(
        server.housefile,
        "g-neo",
        "wrong-local-test-value-000000000001",
    ) == 401


def test_valid_grant_reads_only_its_scoped_view():
    payload = server.housefile("g-neo", GRANT_VALUE)
    assert payload["grant"]["id"] == "g-neo"


def test_grant_token_cannot_cross_owner_boundary():
    assert exception_status(server.require_owner, None) == 401
    assert exception_status(server.require_owner, GRANT_VALUE) == 401
    server.require_owner(OWNER_VALUE)


def test_command_schema_rejects_unknown_verb_and_extra_fields():
    with pytest.raises(ValidationError):
        server.CommandRequest.parse_obj(
            {"grant": "g-neo", "verb": "open-door", "zone": "kitchen"}
        )
    with pytest.raises(ValidationError):
        server.CommandRequest.parse_obj(
            {"grant": "g-neo", "verb": "navigate", "zone": "kitchen", "raw": True}
        )


def test_no_go_command_is_refused():
    body = server.CommandRequest(grant="g-neo", verb="navigate", zone="workshop")
    assert exception_status(server.command, body, GRANT_VALUE) == 403


def test_allowed_command_is_not_claimed_as_relayed_without_adapter():
    body = server.CommandRequest(grant="g-neo", verb="navigate", zone="kitchen")
    with pytest.raises(HTTPException) as caught:
        server.command(body, GRANT_VALUE)
    assert caught.value.status_code == 503
    assert caught.value.detail["relayed"] is False
    assert caught.value.detail["reason"] == "adapter_not_configured"


def test_wrong_scope_and_inactive_grants_are_refused():
    grant = Grant(
        "g-limited-test",
        "Limited Test Agent",
        "agent",
        (Scope.READ_LAYOUT,),
        ("kitchen",),
        credential_digest=token_digest(GRANT_VALUE),
    )
    server.MGR.grants[grant.id] = grant
    try:
        body = server.CommandRequest(grant=grant.id, verb="navigate", zone="kitchen")
        assert exception_status(server.command, body, GRANT_VALUE) == 403
        grant.status = GrantStatus.REVOKED
        assert exception_status(server.housefile, grant.id, GRANT_VALUE) == 403
    finally:
        server.MGR.grants.pop(grant.id, None)


def test_grant_token_is_bound_to_one_grant():
    other = Grant(
        "g-other-test",
        "Other Test Agent",
        "agent",
        (Scope.READ_LAYOUT,),
        ("living",),
        credential_digest=token_digest("other-local-test-value-000000000001"),
    )
    server.MGR.grants[other.id] = other
    try:
        assert exception_status(server.housefile, other.id, GRANT_VALUE) == 401
    finally:
        server.MGR.grants.pop(other.id, None)
