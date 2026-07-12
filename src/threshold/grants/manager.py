"""THS-0013 — issue/revoke/suspend_all. No-go zones are UNGRANTABLE (visible refusal)."""
from __future__ import annotations
from threshold.core.errors import ValidationError
from threshold.core.types import Access, Grant, GrantStatus, Housefile


class GrantManager:
    def __init__(self, file: Housefile):
        self.file = file
        self.grants: dict[str, Grant] = {}

    def issue(self, grant: Grant) -> Grant:
        if not grant.scopes: raise ValidationError("grant needs ≥1 scope")
        if not grant.zones:  raise ValidationError("grant needs ≥1 zone")
        for zid in grant.zones:
            z = self.file.zone(zid)
            if z is None: raise ValidationError(f"unknown zone: {zid}")
            if z.access == Access.NO_GO:
                raise ValidationError(f"zone '{zid}' is no-go: ungrantable")   # SPEC §2
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
