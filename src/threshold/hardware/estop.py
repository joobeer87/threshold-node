"""THS-0041 simulated, latched stop-interlock state machine.

This module performs no hardware I/O and starts no background thread.  A caller
injects the durable grant-suspension/ESTOP receipt boundary, adapter halt
surfaces, clocks, and optional display/receipt observers.  Returned timing is
software-path evidence only; an adapter call completing without an exception is
not proof that a physical device stopped.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Protocol


SIMULATED_TIMING_SCOPE = "simulated_software_path_only"


class InterlockState(str, Enum):
    """Externally visible latch states for the simulated interlock."""

    ARMED = "ARMED"
    TRIPPED = "TRIPPED"


class HaltAdapter(Protocol):
    """Minimum adapter surface exercised by a trip."""

    def halt_all(self) -> object:
        """Attempt the adapter's native halt path."""


class DurableTrip(Protocol):
    """Persist suspension plus one ESTOP receipt for a new latch cycle.

    Implementations must durably record the trip even when zero grants were
    active.  Returning normally reports how many grants were suspended.
    """

    def __call__(self, *, now: datetime) -> int:
        """Commit one trip at the supplied UTC instant."""


@dataclass(frozen=True)
class TripNotice:
    """Sanitized evidence offered to an optional receipt observer."""

    tripped_at: datetime | None
    persistence_succeeded: bool
    suspended_grants: int | None
    adapter_attempts: int
    adapter_completions: int
    adapter_failures: int
    timing_scope: str = SIMULATED_TIMING_SCOPE


@dataclass(frozen=True)
class TripReport:
    """Sanitized result of one new or duplicate simulated trip request."""

    state: InterlockState
    newly_tripped: bool
    tripped_at: datetime | None
    persistence_attempts: int
    persistence_failures: int
    suspended_grants: int | None
    adapter_attempts: int
    adapter_completions: int
    adapter_failures: int
    display_attempts: int
    display_failures: int
    receipt_attempts: int
    receipt_failures: int
    simulated_elapsed_ms: float | None
    timing_scope: str = SIMULATED_TIMING_SCOPE

    @property
    def persistence_succeeded(self) -> bool:
        """Whether the durable callback returned one valid suspension count."""

        return self.persistence_attempts == 1 and self.persistence_failures == 0


UtcClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]
DisplayCallback = Callable[[InterlockState], object]
ReceiptCallback = Callable[[TripNotice], object]


class SimulatedLatchedInterlock:
    """Synchronous fail-closed coordinator for the simulated stop path.

    The latch changes to :attr:`InterlockState.TRIPPED` before any injected
    callback runs.  One durable callback is attempted per latch cycle, every
    configured adapter is attempted independently, and observer failures never
    clear the latch.  ``rearm()`` only clears this local latch; it does not call
    an adapter, restore a grant, or erase the prior report.
    """

    def __init__(
        self,
        durable_trip: DurableTrip,
        adapters: Iterable[HaltAdapter] = (),
        *,
        utc_clock: UtcClock | None = None,
        monotonic_clock: MonotonicClock | None = None,
        display: DisplayCallback | None = None,
        receipt: ReceiptCallback | None = None,
    ) -> None:
        if not callable(durable_trip):
            raise TypeError("durable trip callback is required")
        if utc_clock is not None and not callable(utc_clock):
            raise TypeError("UTC clock is invalid")
        if monotonic_clock is not None and not callable(monotonic_clock):
            raise TypeError("monotonic clock is invalid")
        if display is not None and not callable(display):
            raise TypeError("display callback is invalid")
        if receipt is not None and not callable(receipt):
            raise TypeError("receipt callback is invalid")

        try:
            configured_adapters = tuple(adapters)
        except (TypeError, ValueError):
            raise TypeError("adapter collection is invalid") from None

        self._durable_trip = durable_trip
        self._adapters = configured_adapters
        self._utc_clock = utc_clock or _utc_now
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._display = display
        self._receipt = receipt
        self._state = InterlockState.ARMED
        self._last_report: TripReport | None = None
        self._lock = RLock()

    @property
    def state(self) -> InterlockState:
        """Return the current latch state without invoking any dependency."""

        return self._state

    @property
    def last_report(self) -> TripReport | None:
        """Return immutable evidence for the most recent latch cycle."""

        return self._last_report

    def trip(self) -> TripReport:
        """Latch and run one isolated simulated stop sequence.

        Repeated calls while latched return the original sanitized evidence with
        ``newly_tripped=False`` and perform no callback or adapter call.
        """

        with self._lock:
            if self._state == InterlockState.TRIPPED:
                if self._last_report is None:  # Defensive BaseException boundary.
                    return _empty_tripped_report(newly_tripped=False)
                return replace(self._last_report, newly_tripped=False)

            # Latch first.  Every dependency can observe TRIPPED even if the
            # first clock, persistence, adapter, or observer call fails.
            self._state = InterlockState.TRIPPED
            started = _safe_monotonic(self._monotonic_clock)
            tripped_at = _safe_utc(self._utc_clock)

            display_attempts = int(self._display is not None)
            display_failures = 0
            if self._display is not None:
                try:
                    self._display(InterlockState.TRIPPED)
                except Exception:
                    display_failures = 1

            persistence_attempts = 0
            persistence_failures = 0
            suspended_grants: int | None = None
            if tripped_at is not None:
                persistence_attempts = 1
                try:
                    observed = self._durable_trip(now=tripped_at)
                    if (
                        not isinstance(observed, int)
                        or isinstance(observed, bool)
                        or observed < 0
                    ):
                        raise ValueError("durable callback returned an invalid count")
                    suspended_grants = observed
                except Exception:
                    persistence_failures = 1

            adapter_attempts = 0
            adapter_completions = 0
            for adapter in self._adapters:
                adapter_attempts += 1
                try:
                    adapter.halt_all()
                except Exception:
                    continue
                adapter_completions += 1
            adapter_failures = adapter_attempts - adapter_completions

            persistence_succeeded = (
                persistence_attempts == 1 and persistence_failures == 0
            )
            notice = TripNotice(
                tripped_at=tripped_at,
                persistence_succeeded=persistence_succeeded,
                suspended_grants=suspended_grants,
                adapter_attempts=adapter_attempts,
                adapter_completions=adapter_completions,
                adapter_failures=adapter_failures,
            )
            receipt_attempts = int(self._receipt is not None)
            receipt_failures = 0
            if self._receipt is not None:
                try:
                    self._receipt(notice)
                except Exception:
                    receipt_failures = 1

            finished = _safe_monotonic(self._monotonic_clock)
            report = TripReport(
                state=InterlockState.TRIPPED,
                newly_tripped=True,
                tripped_at=tripped_at,
                persistence_attempts=persistence_attempts,
                persistence_failures=persistence_failures,
                suspended_grants=suspended_grants,
                adapter_attempts=adapter_attempts,
                adapter_completions=adapter_completions,
                adapter_failures=adapter_failures,
                display_attempts=display_attempts,
                display_failures=display_failures,
                receipt_attempts=receipt_attempts,
                receipt_failures=receipt_failures,
                simulated_elapsed_ms=_elapsed_ms(started, finished),
            )
            self._last_report = report
            return report

    def rearm(self) -> bool:
        """Clear only the local latch and return whether it changed state."""

        with self._lock:
            changed = self._state == InterlockState.TRIPPED
            self._state = InterlockState.ARMED
            return changed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_utc(clock: UtcClock) -> datetime | None:
    try:
        value = clock()
        if not isinstance(value, datetime):
            return None
        offset = value.utcoffset()
        if value.tzinfo is None or offset is None:
            return None
        return value.astimezone(timezone.utc)
    except Exception:
        return None


def _safe_monotonic(clock: MonotonicClock) -> float | None:
    try:
        value = clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return None
        return float(value)
    except Exception:
        return None


def _elapsed_ms(started: float | None, finished: float | None) -> float | None:
    if started is None or finished is None or finished < started:
        return None
    return round((finished - started) * 1_000, 3)


def _empty_tripped_report(*, newly_tripped: bool) -> TripReport:
    return TripReport(
        state=InterlockState.TRIPPED,
        newly_tripped=newly_tripped,
        tripped_at=None,
        persistence_attempts=0,
        persistence_failures=0,
        suspended_grants=None,
        adapter_attempts=0,
        adapter_completions=0,
        adapter_failures=0,
        display_attempts=0,
        display_failures=0,
        receipt_attempts=0,
        receipt_failures=0,
        simulated_elapsed_ms=None,
    )
