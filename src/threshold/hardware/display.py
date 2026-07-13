"""THS-0042 deterministic simulated terminal display states.

The display has no clock, sleeper, thread, or event-bus subscription of its own.
Callers pass an aware timestamp for every timed transition and render.  State is
immutable so tests and the simulated interlock can replay the same inputs exactly.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


READ_DURATION = timedelta(seconds=2)
DENY_DURATION = timedelta(seconds=4)
MAX_AGENT_CHARS = 32
MAX_AGENT_INPUT_CHARS = 256
MAX_DISPLAY_GRANTS = 9_999
UNKNOWN_AGENT = "UNKNOWN"
SIMULATED_HEADER = "THRESHOLD DISPLAY [SIMULATED]"


class DisplayInputError(ValueError):
    """A sanitized invalid-input error for the simulated display boundary."""


class DisplayMode(str, Enum):
    ARMED = "ARMED"
    READ = "READ"
    DENY = "DENY"
    TRIPPED = "TRIPPED"


@dataclass(frozen=True)
class DisplayFrame:
    """One deterministic frame suitable for a terminal or future device adapter."""

    mode: DisplayMode
    active_grants: int
    agent: str | None = None


@dataclass(frozen=True)
class _Transient:
    mode: DisplayMode
    agent: str
    started_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class DisplayState:
    """Immutable state machine for ARMED, transient, and latched display modes."""

    tripped: bool = False
    _transient: _Transient | None = None

    def on_read(self, agent: object, *, now: object) -> "DisplayState":
        """Show READ for two seconds unless TRIPPED is latched."""

        return self._with_transient(DisplayMode.READ, agent, now, READ_DURATION)

    def on_deny(self, agent: object, *, now: object) -> "DisplayState":
        """Show DENY for four seconds unless TRIPPED is latched."""

        return self._with_transient(DisplayMode.DENY, agent, now, DENY_DURATION)

    def trip(self) -> "DisplayState":
        """Latch TRIPPED and discard any transient frame."""

        if self.tripped and self._transient is None:
            return self
        return DisplayState(tripped=True)

    def rearm(self) -> "DisplayState":
        """Explicitly clear only the display latch; no grant state is restored."""

        if not self.tripped:
            return self
        return DisplayState()

    def frame(self, *, active_grants: object, now: object) -> DisplayFrame:
        """Resolve the visible frame at one caller-supplied instant."""

        grant_count = _grant_count(active_grants)
        current = _utc(now)
        if self.tripped:
            return DisplayFrame(DisplayMode.TRIPPED, grant_count)
        transient = self._transient
        if (
            transient is not None
            and transient.started_at <= current < transient.expires_at
        ):
            return DisplayFrame(transient.mode, grant_count, transient.agent)
        return DisplayFrame(DisplayMode.ARMED, grant_count)

    def _with_transient(
        self,
        mode: DisplayMode,
        agent: object,
        now: object,
        duration: timedelta,
    ) -> "DisplayState":
        if self.tripped:
            return self
        started_at = _utc(now)
        return DisplayState(
            _transient=_Transient(
                mode=mode,
                agent=sanitize_agent(agent),
                started_at=started_at,
                expires_at=started_at + duration,
            )
        )


def sanitize_agent(value: object) -> str:
    """Return bounded printable text that cannot inject terminal controls."""

    if not isinstance(value, str):
        return UNKNOWN_AGENT
    normalized = unicodedata.normalize("NFKC", value[:MAX_AGENT_INPUT_CHARS])
    characters: list[str] = []
    for character in normalized:
        if character.isspace():
            characters.append(" ")
        elif not unicodedata.category(character).startswith("C"):
            characters.append(character)
    cleaned = " ".join("".join(characters).split())
    return cleaned[:MAX_AGENT_CHARS] or UNKNOWN_AGENT


def render_terminal(frame: DisplayFrame) -> str:
    """Render one plain-text frame with an unmistakable simulation label."""

    if not isinstance(frame, DisplayFrame):
        raise DisplayInputError("display frame is invalid")
    grant_count = _grant_count(frame.active_grants)
    if frame.mode == DisplayMode.ARMED:
        noun = "GRANT" if grant_count == 1 else "GRANTS"
        body = f"ARMED {grant_count} {noun}"
    elif frame.mode in {DisplayMode.READ, DisplayMode.DENY}:
        agent = sanitize_agent(frame.agent)
        body = f"{frame.mode.value} {agent}"
    else:
        body = "TRIPPED"
    return f"{SIMULATED_HEADER}\n{body}"


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise DisplayInputError("display clock is invalid")
    try:
        offset = value.utcoffset()
        if value.tzinfo is None or offset is None:
            raise DisplayInputError("display clock is invalid")
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise DisplayInputError("display clock is invalid") from exc


def _grant_count(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= MAX_DISPLAY_GRANTS
    ):
        raise DisplayInputError("active grant count is invalid")
    return value
