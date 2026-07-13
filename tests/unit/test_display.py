"""Deterministic proofs for the THS-0042 simulated terminal display."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from threshold.hardware.display import (
    DENY_DURATION,
    MAX_AGENT_CHARS,
    READ_DURATION,
    DisplayFrame,
    DisplayInputError,
    DisplayMode,
    DisplayState,
    render_terminal,
    sanitize_agent,
)


NOW = datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)


def test_armed_frame_contains_the_current_grant_count() -> None:
    state = DisplayState()

    assert state.frame(active_grants=0, now=NOW) == DisplayFrame(
        DisplayMode.ARMED, 0
    )
    assert render_terminal(state.frame(active_grants=1, now=NOW)) == (
        "THRESHOLD DISPLAY [SIMULATED]\nARMED 1 GRANT"
    )
    assert render_terminal(state.frame(active_grants=3, now=NOW)) == (
        "THRESHOLD DISPLAY [SIMULATED]\nARMED 3 GRANTS"
    )


def test_read_is_start_inclusive_and_expires_at_exactly_two_seconds() -> None:
    state = DisplayState().on_read("Synthetic Reader", now=NOW)

    assert state.frame(active_grants=2, now=NOW).mode == DisplayMode.READ
    assert state.frame(
        active_grants=2,
        now=NOW + READ_DURATION - timedelta(microseconds=1),
    ).mode == DisplayMode.READ
    assert state.frame(
        active_grants=2,
        now=NOW + READ_DURATION,
    ) == DisplayFrame(DisplayMode.ARMED, 2)


def test_deny_is_start_inclusive_and_expires_at_exactly_four_seconds() -> None:
    state = DisplayState().on_deny("Synthetic Agent", now=NOW)

    frame = state.frame(
        active_grants=2,
        now=NOW + DENY_DURATION - timedelta(microseconds=1),
    )
    assert frame == DisplayFrame(DisplayMode.DENY, 2, "Synthetic Agent")
    assert render_terminal(frame) == (
        "THRESHOLD DISPLAY [SIMULATED]\nDENY Synthetic Agent"
    )
    assert state.frame(
        active_grants=2,
        now=NOW + DENY_DURATION,
    ).mode == DisplayMode.ARMED


def test_latest_transient_event_replaces_the_previous_one() -> None:
    state = DisplayState().on_read("First Reader", now=NOW)
    assert state.rearm() is state
    state = state.on_deny("Second Agent", now=NOW + timedelta(seconds=1))

    assert state.frame(
        active_grants=1,
        now=NOW + timedelta(seconds=2),
    ) == DisplayFrame(DisplayMode.DENY, 1, "Second Agent")


def test_tripped_is_latched_and_has_precedence_until_explicit_rearm() -> None:
    tripped = DisplayState().on_read("Synthetic Reader", now=NOW).trip()

    assert tripped.frame(
        active_grants=7,
        now=NOW + timedelta(days=1),
    ) == DisplayFrame(DisplayMode.TRIPPED, 7)
    assert tripped.on_deny("ignored\nagent", now=None) is tripped
    assert render_terminal(tripped.frame(active_grants=7, now=NOW)) == (
        "THRESHOLD DISPLAY [SIMULATED]\nTRIPPED"
    )

    rearmed = tripped.rearm()
    assert rearmed.frame(active_grants=0, now=NOW) == DisplayFrame(
        DisplayMode.ARMED, 0
    )


def test_agent_text_is_bounded_and_cannot_inject_terminal_controls() -> None:
    raw = "Neo\n\x1b[31m\tUnit\x7f\u202e" + "A" * 100
    sanitized = sanitize_agent(raw)
    frame = DisplayState().on_deny(raw, now=NOW).frame(
        active_grants=1,
        now=NOW,
    )
    rendered = render_terminal(frame)

    assert sanitized == frame.agent
    assert len(sanitized) == MAX_AGENT_CHARS
    assert "Neo [31m Unit" in sanitized
    assert "\x1b" not in rendered
    assert "\n" not in rendered.splitlines()[1]
    assert "\r" not in rendered
    assert "\u202e" not in rendered
    assert all(character.isprintable() for character in sanitized)


@pytest.mark.parametrize("agent", [None, 42, "\x00\n\t\u202e"])
def test_missing_or_control_only_agent_uses_a_safe_placeholder(agent: object) -> None:
    assert sanitize_agent(agent) == "UNKNOWN"


@pytest.mark.parametrize(
    "clock",
    [None, "2026-07-16T14:00:00Z", datetime(2026, 7, 16, 14, 0)],
)
def test_invalid_clock_is_rejected_without_reflecting_it(clock: object) -> None:
    with pytest.raises(DisplayInputError, match="display clock is invalid"):
        DisplayState().frame(active_grants=0, now=clock)


@pytest.mark.parametrize("count", [-1, True, 10_000, 1.5, "1"])
def test_invalid_grant_count_is_rejected(count: object) -> None:
    with pytest.raises(DisplayInputError, match="active grant count is invalid"):
        DisplayState().frame(active_grants=count, now=NOW)

    with pytest.raises(DisplayInputError, match="active grant count is invalid"):
        render_terminal(DisplayFrame(DisplayMode.ARMED, count))  # type: ignore[arg-type]


def test_same_state_clock_and_count_render_identically() -> None:
    state = DisplayState().on_read("Synthetic Reader", now=NOW)

    first = render_terminal(state.frame(active_grants=2, now=NOW))
    second = render_terminal(state.frame(active_grants=2, now=NOW))

    assert first == second
