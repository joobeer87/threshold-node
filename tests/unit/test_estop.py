"""Deterministic proofs for the THS-0041 simulated latched interlock."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from threshold.hardware.estop import (
    SIMULATED_TIMING_SCOPE,
    InterlockState,
    SimulatedLatchedInterlock,
    TripNotice,
    TripReport,
)


LOCAL_NOW = datetime(
    2026,
    7,
    16,
    10,
    30,
    tzinfo=timezone(timedelta(hours=-4)),
)
UTC_NOW = datetime(2026, 7, 16, 14, 30, tzinfo=timezone.utc)


class SyntheticAdapter:
    def __init__(
        self,
        label: str,
        events: list[str],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.label = label
        self.events = events
        self.failure = failure
        self.calls = 0

    def halt_all(self) -> dict[str, object]:
        self.calls += 1
        self.events.append(self.label)
        if self.failure is not None:
            raise self.failure
        # Completion is deliberately not described as physical halt evidence.
        return {"synthetic_adapter_call_completed": True}


def monotonic_values(*values: float):
    sequence = iter(values)
    return lambda: next(sequence)


def test_trip_latches_first_persists_zero_grants_and_attempts_every_adapter() -> None:
    events: list[str] = []
    notices: list[TripNotice] = []
    holder: dict[str, SimulatedLatchedInterlock] = {}

    def display(state: InterlockState) -> None:
        assert holder["interlock"].state == InterlockState.TRIPPED
        assert state == InterlockState.TRIPPED
        events.append("display")

    def durable_trip(*, now: datetime) -> int:
        assert holder["interlock"].state == InterlockState.TRIPPED
        assert now == UTC_NOW
        events.append("persist")
        return 0

    def receipt(notice: TripNotice) -> None:
        assert holder["interlock"].state == InterlockState.TRIPPED
        notices.append(notice)
        events.append("receipt")

    adapters = (
        SyntheticAdapter("adapter-one", events),
        SyntheticAdapter(
            "adapter-failed",
            events,
            failure=RuntimeError("private synthetic adapter detail"),
        ),
        SyntheticAdapter("adapter-three", events),
    )
    interlock = SimulatedLatchedInterlock(
        durable_trip,
        adapters,
        utc_clock=lambda: LOCAL_NOW,
        monotonic_clock=monotonic_values(40.0, 40.025),
        display=display,
        receipt=receipt,
    )
    holder["interlock"] = interlock

    report = interlock.trip()

    assert events == [
        "display",
        "persist",
        "adapter-one",
        "adapter-failed",
        "adapter-three",
        "receipt",
    ]
    assert interlock.state == InterlockState.TRIPPED
    assert report.state == InterlockState.TRIPPED
    assert report.newly_tripped is True
    assert report.tripped_at == UTC_NOW
    assert report.persistence_succeeded is True
    assert report.persistence_attempts == 1
    assert report.persistence_failures == 0
    assert report.suspended_grants == 0
    assert report.adapter_attempts == 3
    assert report.adapter_completions == 2
    assert report.adapter_failures == 1
    assert report.display_attempts == 1
    assert report.display_failures == 0
    assert report.receipt_attempts == 1
    assert report.receipt_failures == 0
    assert report.simulated_elapsed_ms == 25.0
    assert report.timing_scope == SIMULATED_TIMING_SCOPE
    assert notices == [
        TripNotice(
            tripped_at=UTC_NOW,
            persistence_succeeded=True,
            suspended_grants=0,
            adapter_attempts=3,
            adapter_completions=2,
            adapter_failures=1,
        )
    ]
    with pytest.raises(FrozenInstanceError):
        report.adapter_failures = 99  # type: ignore[misc]


def test_failures_are_isolated_sanitized_and_never_clear_the_latch() -> None:
    events: list[str] = []
    received: list[TripNotice] = []

    def fail_persistence(*, now: datetime) -> int:
        assert now == UTC_NOW
        events.append("persist-failed")
        raise OSError("private store path and receipt detail")

    def fail_display(_state: InterlockState) -> None:
        events.append("display-failed")
        raise RuntimeError("private display detail")

    def fail_receipt(notice: TripNotice) -> None:
        received.append(notice)
        events.append("receipt-failed")
        raise RuntimeError("private printer detail")

    adapters = (
        SyntheticAdapter(
            "adapter-one-failed",
            events,
            failure=RuntimeError("private first adapter detail"),
        ),
        SyntheticAdapter("adapter-two-completed", events),
        SyntheticAdapter(
            "adapter-three-failed",
            events,
            failure=OSError("private third adapter detail"),
        ),
    )
    interlock = SimulatedLatchedInterlock(
        fail_persistence,
        adapters,
        utc_clock=lambda: UTC_NOW,
        monotonic_clock=monotonic_values(1.0, 1.01),
        display=fail_display,
        receipt=fail_receipt,
    )

    report = interlock.trip()

    assert events == [
        "display-failed",
        "persist-failed",
        "adapter-one-failed",
        "adapter-two-completed",
        "adapter-three-failed",
        "receipt-failed",
    ]
    assert interlock.state == InterlockState.TRIPPED
    assert report.persistence_succeeded is False
    assert report.persistence_attempts == 1
    assert report.persistence_failures == 1
    assert report.suspended_grants is None
    assert report.adapter_attempts == 3
    assert report.adapter_completions == 1
    assert report.adapter_failures == 2
    assert report.display_failures == 1
    assert report.receipt_failures == 1
    assert received[0].persistence_succeeded is False
    rendered = repr(report) + repr(received)
    assert "private" not in rendered
    assert "adapter-one" not in rendered
    assert "printer" not in rendered


def test_repeated_trip_is_idempotent_without_any_duplicate_side_effect() -> None:
    calls = {"persist": 0, "adapter": 0, "display": 0, "receipt": 0}

    def persist(*, now: datetime) -> int:
        calls["persist"] += 1
        return 2

    class Adapter:
        def halt_all(self) -> None:
            calls["adapter"] += 1

    def display(_state: InterlockState) -> None:
        calls["display"] += 1

    def receipt(_notice: TripNotice) -> None:
        calls["receipt"] += 1

    interlock = SimulatedLatchedInterlock(
        persist,
        (Adapter(),),
        utc_clock=lambda: UTC_NOW,
        monotonic_clock=monotonic_values(10.0, 10.02),
        display=display,
        receipt=receipt,
    )

    first = interlock.trip()
    repeated = interlock.trip()
    repeated_again = interlock.trip()

    assert calls == {"persist": 1, "adapter": 1, "display": 1, "receipt": 1}
    assert first.newly_tripped is True
    assert repeated.newly_tripped is False
    assert repeated_again.newly_tripped is False
    assert repeated.tripped_at == first.tripped_at
    assert repeated.simulated_elapsed_ms == first.simulated_elapsed_ms
    assert repeated.adapter_attempts == first.adapter_attempts
    assert interlock.last_report is first


def test_concurrent_trip_signals_share_one_latch_cycle() -> None:
    calls = {"persist": 0, "adapter": 0}
    barrier = threading.Barrier(9)

    def persist(*, now: datetime) -> int:
        calls["persist"] += 1
        return 0

    class Adapter:
        def halt_all(self) -> None:
            calls["adapter"] += 1

    interlock = SimulatedLatchedInterlock(
        persist,
        (Adapter(),),
        utc_clock=lambda: UTC_NOW,
        monotonic_clock=monotonic_values(1.0, 1.01),
    )

    def signal() -> TripReport:
        barrier.wait()
        return interlock.trip()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(signal) for _ in range(8)]
        barrier.wait()
        reports = [future.result(timeout=5) for future in futures]

    assert calls == {"persist": 1, "adapter": 1}
    assert sum(report.newly_tripped for report in reports) == 1
    assert all(report.state == InterlockState.TRIPPED for report in reports)


def test_rearm_only_clears_latch_and_a_later_trip_starts_a_new_cycle() -> None:
    calls = {"persist": 0, "adapter": 0}

    def persist(*, now: datetime) -> int:
        calls["persist"] += 1
        return 1 if calls["persist"] == 1 else 0

    class Adapter:
        def halt_all(self) -> None:
            calls["adapter"] += 1

    interlock = SimulatedLatchedInterlock(
        persist,
        (Adapter(),),
        utc_clock=lambda: UTC_NOW,
        monotonic_clock=monotonic_values(1.0, 1.01, 2.0, 2.02),
    )
    first = interlock.trip()

    assert interlock.rearm() is True
    assert interlock.state == InterlockState.ARMED
    assert interlock.last_report is first
    assert calls == {"persist": 1, "adapter": 1}
    assert interlock.rearm() is False
    assert calls == {"persist": 1, "adapter": 1}

    second = interlock.trip()
    assert second.newly_tripped is True
    assert second.suspended_grants == 0
    assert interlock.state == InterlockState.TRIPPED
    assert calls == {"persist": 2, "adapter": 2}


@pytest.mark.parametrize("invalid_count", [-1, True, None, "1"])
def test_invalid_durable_callback_result_fails_closed(invalid_count: object) -> None:
    adapter = SyntheticAdapter("adapter", [])

    def persist(*, now: datetime):
        return invalid_count

    interlock = SimulatedLatchedInterlock(
        persist,
        (adapter,),
        utc_clock=lambda: UTC_NOW,
        monotonic_clock=monotonic_values(3.0, 3.001),
    )

    report = interlock.trip()

    assert interlock.state == InterlockState.TRIPPED
    assert report.persistence_attempts == 1
    assert report.persistence_failures == 1
    assert report.persistence_succeeded is False
    assert report.suspended_grants is None
    assert adapter.calls == 1


def test_invalid_clocks_do_not_prevent_adapter_attempts_or_clear_the_latch() -> None:
    durable_calls = 0
    adapter = SyntheticAdapter("adapter", [])

    def persist(*, now: datetime) -> int:
        nonlocal durable_calls
        durable_calls += 1
        return 1

    interlock = SimulatedLatchedInterlock(
        persist,
        (adapter,),
        utc_clock=lambda: datetime(2026, 7, 16, 14, 30),
        monotonic_clock=lambda: float("nan"),
    )

    report = interlock.trip()

    assert interlock.state == InterlockState.TRIPPED
    assert report.tripped_at is None
    assert report.persistence_attempts == 0
    assert report.persistence_succeeded is False
    assert report.simulated_elapsed_ms is None
    assert report.timing_scope == SIMULATED_TIMING_SCOPE
    assert durable_calls == 0
    assert adapter.calls == 1
