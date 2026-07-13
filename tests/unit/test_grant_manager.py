"""Time-bound and lifecycle behavior for grants."""

from datetime import datetime, timedelta, timezone

import pytest

from threshold.capture.seed import SEED_FILE
from threshold.core.auth import token_digest
from threshold.core.errors import ValidationError
from threshold.core.types import Grant, GrantStatus, Scope
from threshold.grants.manager import GrantManager


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def grant(**changes) -> Grant:
    values = {
        "id": "g-time-test",
        "name": "Time Test Agent",
        "kind": "agent",
        "scopes": (Scope.READ_LAYOUT, Scope.CMD_NAVIGATE),
        "zones": ("kitchen",),
        "window": "standing",
        "expires": "revocable",
    }
    values.update(changes)
    return Grant(**values)


def test_issue_rejects_duplicate_id():
    manager = GrantManager(SEED_FILE)
    manager.issue(grant(), now=NOW)
    with pytest.raises(ValidationError, match="already exists"):
        manager.issue(grant(), now=NOW)


def test_issue_rejects_duplicate_credential_digest():
    manager = GrantManager(SEED_FILE)
    digest = token_digest("synthetic-grant-token-000000000001")
    manager.issue(grant(credential_digest=digest), now=NOW)
    with pytest.raises(ValidationError, match="credential"):
        manager.issue(
            grant(id="g-other-time-test", credential_digest=digest),
            now=NOW,
        )


def test_issue_rejects_expired_or_timezone_free_expiration():
    manager = GrantManager(SEED_FILE)
    with pytest.raises(ValidationError, match="future"):
        manager.issue(grant(expires=timestamp(NOW - timedelta(seconds=1))), now=NOW)
    with pytest.raises(ValidationError, match="RFC 3339"):
        manager.issue(grant(id="g-naive", expires="2026-07-16T12:00:00"), now=NOW)


@pytest.mark.parametrize(
    "invalid",
    [
        "20260716T120000Z",
        "2026-W29-4T12:00:00Z",
        "2026-07-16 12:00:00Z",
        "2026-07-16T12:00Z",
    ],
)
def test_issue_enforces_the_documented_rfc3339_grammar(invalid):
    with pytest.raises(ValidationError, match="RFC 3339"):
        GrantManager(SEED_FILE).issue(grant(expires=invalid), now=NOW)


def test_expiration_is_enforced_and_updates_status():
    manager = GrantManager(SEED_FILE)
    item = grant(expires=timestamp(NOW + timedelta(minutes=5)))
    manager.issue(item, now=NOW)
    assert manager.decision(item, now=NOW).allowed is True

    decision = manager.decision(item, now=NOW + timedelta(minutes=5))
    assert decision.allowed is False
    assert decision.reason == "grant_expired"
    assert decision.next_status == GrantStatus.EXPIRED
    assert item.status == GrantStatus.ACTIVE


def test_one_time_window_is_start_inclusive_and_end_exclusive():
    manager = GrantManager(SEED_FILE)
    start = NOW + timedelta(hours=1)
    end = NOW + timedelta(hours=2)
    item = grant(window=f"{timestamp(start)}/{timestamp(end)}")
    manager.issue(item, now=NOW)

    assert manager.decision(item, now=NOW).reason == "grant_outside_window"
    assert manager.decision(item, now=start).allowed is True
    assert manager.decision(item, now=end - timedelta(microseconds=1)).allowed is True
    decision = manager.decision(item, now=end)
    assert decision.reason == "grant_expired"
    assert decision.next_status == GrantStatus.EXPIRED
    assert item.status == GrantStatus.ACTIVE


def test_expiration_must_leave_a_non_empty_window():
    manager = GrantManager(SEED_FILE)
    start = NOW + timedelta(hours=1)
    end = NOW + timedelta(hours=2)
    with pytest.raises(ValidationError, match="after window start"):
        manager.issue(
            grant(
                window=f"{timestamp(start)}/{timestamp(end)}",
                expires=timestamp(start),
            ),
            now=NOW,
        )


def test_invalid_existing_time_policy_fails_closed():
    manager = GrantManager(SEED_FILE)
    assert manager.decision(grant(window="morning-ish"), now=NOW).reason == (
        "grant_invalid_window"
    )
    assert manager.decision(grant(expires="later"), now=NOW).reason == (
        "grant_invalid_expiry"
    )
    assert manager.decision(grant(window=None), now=NOW).reason == (
        "grant_invalid_window"
    )
    assert manager.decision(grant(expires=None), now=NOW).reason == (
        "grant_invalid_expiry"
    )


def test_inactive_status_is_refused_before_time_evaluation():
    manager = GrantManager(SEED_FILE)
    item = grant(status=GrantStatus.REVOKED, expires="not-a-timestamp")
    assert manager.decision(item, now=NOW).reason == "grant_revoked"


def test_naive_evaluation_clock_fails_closed():
    manager = GrantManager(SEED_FILE)
    naive = datetime(2026, 7, 15, 12, 0)
    assert manager.decision(grant(), now=naive).reason == "grant_invalid_clock"
    with pytest.raises(ValidationError, match="current time"):
        manager.issue(grant(), now=naive)
    assert manager.decision(grant(), now="not-a-clock").reason == "grant_invalid_clock"
