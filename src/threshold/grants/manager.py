"""Grant lifecycle and time-bound access decisions."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hmac import compare_digest

from threshold.core.errors import ValidationError
from threshold.core.types import Access, Grant, GrantStatus, Housefile


REVOCABLE = "revocable"
STANDING = "standing"
RFC3339_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


@dataclass(frozen=True)
class GrantDecision:
    allowed: bool
    reason: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_time(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValidationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must include a timezone offset")
    return value.astimezone(timezone.utc)


def parse_timestamp(value: str, field_name: str) -> datetime:
    """Parse an RFC 3339 timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not RFC3339_TIMESTAMP.fullmatch(value):
        raise ValidationError(f"{field_name} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be an RFC 3339 timestamp") from exc
    return normalize_time(parsed, field_name)


def parse_window(value: str) -> tuple[datetime, datetime] | None:
    """Return a one-time UTC interval, or ``None`` for a standing grant."""
    if not isinstance(value, str):
        raise ValidationError(
            "window must be 'standing' or '<RFC3339 start>/<RFC3339 end>'"
        )
    if value == STANDING:
        return None
    parts = value.split("/")
    if len(parts) != 2:
        raise ValidationError(
            "window must be 'standing' or '<RFC3339 start>/<RFC3339 end>'"
        )
    start = parse_timestamp(parts[0], "window start")
    end = parse_timestamp(parts[1], "window end")
    if start >= end:
        raise ValidationError("window start must be before window end")
    return start, end


class GrantManager:
    def __init__(self, file: Housefile):
        self.file = file
        self.grants: dict[str, Grant] = {}

    def issue(self, grant: Grant, *, now: datetime | None = None) -> Grant:
        if grant.id in self.grants:
            raise ValidationError("grant id already exists")
        if grant.credential_digest and any(
            existing.credential_digest
            and compare_digest(grant.credential_digest, existing.credential_digest)
            for existing in self.grants.values()
        ):
            raise ValidationError("grant credential is already registered")
        if not grant.scopes: raise ValidationError("grant needs ≥1 scope")
        if not grant.zones:  raise ValidationError("grant needs ≥1 zone")
        for zid in grant.zones:
            z = self.file.zone(zid)
            if z is None: raise ValidationError(f"unknown zone: {zid}")
            if z.access == Access.NO_GO:
                raise ValidationError(f"zone '{zid}' is no-go: ungrantable")   # SPEC §2
        current = normalize_time(now or utc_now(), "current time")
        expires_at: datetime | None = None
        if grant.expires != REVOCABLE:
            expires_at = parse_timestamp(grant.expires, "expires")
            if expires_at <= current:
                raise ValidationError("expires must be in the future")
        window = parse_window(grant.window)
        if window is not None and window[1] <= current:
            raise ValidationError("window end must be in the future")
        if window is not None and expires_at is not None and expires_at <= window[0]:
            raise ValidationError("expires must be after window start")
        self.grants[grant.id] = grant
        return grant

    def revoke(self, grant_id: str) -> Grant:
        g = self.grants[grant_id]; g.status = GrantStatus.REVOKED; return g

    def suspend_all(self) -> int:
        """E-stop path. Returns count suspended."""
        n = 0
        for g in self.grants.values():
            if g.status == GrantStatus.ACTIVE:
                g.status = GrantStatus.SUSPENDED; n += 1
        return n

    def decision(self, grant: Grant, *, now: datetime | None = None) -> GrantDecision:
        """Evaluate whether a grant is usable without exposing any resource data."""
        if grant.status != GrantStatus.ACTIVE:
            return GrantDecision(False, f"grant_{grant.status.value}")

        try:
            current = normalize_time(now or utc_now(), "current time")
        except ValidationError:
            return GrantDecision(False, "grant_invalid_clock")
        if grant.expires != REVOCABLE:
            try:
                expires_at = parse_timestamp(grant.expires, "expires")
            except ValidationError:
                return GrantDecision(False, "grant_invalid_expiry")
            if current >= expires_at:
                grant.status = GrantStatus.EXPIRED
                return GrantDecision(False, "grant_expired")

        try:
            window = parse_window(grant.window)
        except ValidationError:
            return GrantDecision(False, "grant_invalid_window")
        if window is not None:
            if current >= window[1]:
                grant.status = GrantStatus.EXPIRED
                return GrantDecision(False, "grant_expired")
            if current < window[0]:
                return GrantDecision(False, "grant_outside_window")
        return GrantDecision(True, "grant_active")
