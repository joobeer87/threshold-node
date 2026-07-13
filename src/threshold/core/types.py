"""Core types — the lingua franca. THS-0002. SPEC-THS-0.1 §1–2."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Access(str, Enum):
    OPEN = "open"; RESTRICTED = "restricted"; NO_GO = "no-go"

class Scope(str, Enum):
    READ_LAYOUT = "read:layout"; READ_SYSTEMS = "read:systems"; READ_INVENTORY = "read:inventory"
    CMD_NAVIGATE = "command:navigate"; CMD_MANIPULATE = "command:manipulate"

class GrantStatus(str, Enum):
    ACTIVE = "active"; REVOKED = "revoked"; EXPIRED = "expired"; SUSPENDED = "suspended"

class Tier(str, Enum):
    ENFORCED = "ENFORCED"; GATED = "GATED"; ADVISORY = "ADVISORY"

class EventType(str, Enum):
    GRANT = "GRANT"; READ = "READ"; DENY = "DENY"; REVOKE = "REVOKE"; ESTOP = "ESTOP"; PROVISION = "PROVISION"

SAFETY_FLAGS = frozenset({"fragile", "do-not-touch"})


@dataclass(frozen=True)
class Zone:
    id: str; name: str; access: Access
    boundary: tuple[float, float, float, float]
    note: str = ""; outdoor: bool = False
    def __post_init__(self):
        if len(self.boundary) != 4: raise ValueError(f"zone {self.id}: boundary must be [x,y,w,h]")

@dataclass(frozen=True)
class SystemItem:
    id: str; name: str; zone: str; tag: str; detail: str

@dataclass(frozen=True)
class InventoryItem:
    id: str; name: str; zone: str
    flags: tuple[str, ...] = (); note: str = ""

@dataclass(frozen=True)
class Quirk:
    id: str; zone: str; text: str

@dataclass(frozen=True)
class Policies:
    quiet_start: str = "21:30"; quiet_end: str = "06:30"
    timezone: str = "Etc/UTC"
    teleop: str = "per-session"; residency: str = "local-first"

@dataclass(frozen=True)
class Housefile:
    dwelling_name: str
    zones: tuple[Zone, ...]
    systems: tuple[SystemItem, ...] = ()
    inventory: tuple[InventoryItem, ...] = ()
    quirks: tuple[Quirk, ...] = ()
    policies: Policies = field(default_factory=Policies)
    schema: str = "ths/0.1"; rev: str = "A"
    def zone(self, zid: str) -> Zone | None:
        return next((z for z in self.zones if z.id == zid), None)

@dataclass
class Grant:
    id: str; name: str; kind: str
    scopes: tuple[Scope, ...]; zones: tuple[str, ...]
    window: str = "standing"; expires: str = "revocable"
    status: GrantStatus = GrantStatus.ACTIVE; issued: str = ""
    credential_digest: str = field(default="", repr=False)
