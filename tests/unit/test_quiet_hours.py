"""Focused proofs for pure command quiet-hours decisions."""

from datetime import datetime, timedelta, timezone

import pytest

from threshold.core.quiet_hours import evaluate_command_quiet_hours


UTC = timezone.utc


def at(hour: int, minute: int, second: int = 0, *, tz: timezone = UTC) -> datetime:
    return datetime(2026, 7, 13, hour, minute, second, tzinfo=tz)


@pytest.mark.parametrize(
    ("current", "allowed"),
    [
        (at(8, 59, 59), True),
        (at(9, 0), False),
        (at(9, 0, 59), False),
        (at(16, 59, 59), False),
        (at(17, 0), True),
    ],
)
def test_same_day_interval_is_start_inclusive_and_end_exclusive(
    current: datetime,
    allowed: bool,
) -> None:
    decision = evaluate_command_quiet_hours("09:00", "17:00", now=current)

    assert decision.allowed is allowed
    assert decision.reason == (
        "outside_quiet_hours" if allowed else "quiet_hours_active"
    )


@pytest.mark.parametrize(
    ("current", "allowed"),
    [
        (at(21, 29, 59), True),
        (at(21, 30), False),
        (at(23, 59, 59), False),
        (at(0, 0), False),
        (at(6, 29, 59), False),
        (at(6, 30), True),
    ],
)
def test_overnight_interval_wraps_across_midnight(
    current: datetime,
    allowed: bool,
) -> None:
    decision = evaluate_command_quiet_hours("21:30", "06:30", now=current)

    assert decision.allowed is allowed


@pytest.mark.parametrize("current", [at(0, 0), at(12, 0), at(23, 59, 59)])
def test_equal_boundaries_mean_quiet_all_day(current: datetime) -> None:
    decision = evaluate_command_quiet_hours("07:15", "07:15", now=current)

    assert decision.allowed is False
    assert decision.reason == "quiet_hours_active"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("7:00", "08:00"),
        ("07:0", "08:00"),
        (" 07:00", "08:00"),
        ("07:00 ", "08:00"),
        ("07:00\n", "08:00"),
        ("24:00", "08:00"),
        ("07:60", "08:00"),
        ("07：00", "08:00"),
        (None, "08:00"),
        ("07:00", 800),
    ],
)
def test_malformed_policy_fails_closed(start: object, end: object) -> None:
    decision = evaluate_command_quiet_hours(start, end, now=at(12, 0))

    assert decision.allowed is False
    assert decision.reason == "quiet_hours_invalid"


@pytest.mark.parametrize(
    "current",
    [
        datetime(2026, 7, 13, 12, 0),
        None,
        "2026-07-13T12:00:00Z",
    ],
)
def test_missing_or_naive_clock_fails_closed(current: object) -> None:
    decision = evaluate_command_quiet_hours("21:30", "06:30", now=current)

    assert decision.allowed is False
    assert decision.reason == "quiet_hours_clock_invalid"


def test_aware_clock_uses_the_supplied_policy_timezone_wall_time() -> None:
    eastern_summer = timezone(timedelta(hours=-4))

    active = evaluate_command_quiet_hours(
        "21:30", "06:30", now=at(22, 0, tz=eastern_summer)
    )
    inactive = evaluate_command_quiet_hours(
        "21:30", "06:30", now=at(12, 0, tz=eastern_summer)
    )

    assert active.allowed is False
    assert inactive.allowed is True
