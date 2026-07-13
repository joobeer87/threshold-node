"""Pure quiet-hours decisions for command gating.

The caller supplies an aware ``datetime`` already expressed in the household's
policy timezone.  Equal start and end values mean quiet hours are active all
day; this is the safer fail-closed interpretation for an otherwise ambiguous
command policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


_HH_MM = re.compile(r"([0-9]{2}):([0-9]{2})\Z")


@dataclass(frozen=True)
class QuietHoursDecision:
    """Result of evaluating quiet hours for a command request."""

    allowed: bool
    reason: str


def _minute_of_day(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = _HH_MM.fullmatch(value)
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def evaluate_command_quiet_hours(
    quiet_start: object,
    quiet_end: object,
    *,
    now: object,
) -> QuietHoursDecision:
    """Return whether a command may proceed under the quiet-hours policy.

    Intervals are start-inclusive and end-exclusive.  Overnight intervals
    wrap across midnight.  Malformed policy values and missing/naive clocks
    deny the command instead of raising or silently disabling the policy.
    This function is intentionally command-specific; quiet hours do not gate
    housefile reads or other disclosures.
    """

    start_minute = _minute_of_day(quiet_start)
    end_minute = _minute_of_day(quiet_end)
    if start_minute is None or end_minute is None:
        return QuietHoursDecision(False, "quiet_hours_invalid")

    if not isinstance(now, datetime):
        return QuietHoursDecision(False, "quiet_hours_clock_invalid")
    try:
        offset = now.utcoffset()
    except (OverflowError, ValueError):
        return QuietHoursDecision(False, "quiet_hours_clock_invalid")
    if now.tzinfo is None or offset is None:
        return QuietHoursDecision(False, "quiet_hours_clock_invalid")

    if start_minute == end_minute:
        return QuietHoursDecision(False, "quiet_hours_active")

    current_minute = now.hour * 60 + now.minute
    if start_minute < end_minute:
        quiet = start_minute <= current_minute < end_minute
    else:
        quiet = current_minute >= start_minute or current_minute < end_minute

    if quiet:
        return QuietHoursDecision(False, "quiet_hours_active")
    return QuietHoursDecision(True, "outside_quiet_hours")
