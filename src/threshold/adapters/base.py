"""Adapter contract. Tier is COMPUTED from capabilities — never asserted (T-ENF-01)."""
from __future__ import annotations
from dataclasses import dataclass
from threshold.core.types import Housefile, Tier

@dataclass
class Capabilities:
    areas: bool = False; stayout: bool = False; halt: bool = False

class BaseAdapter:
    name = "base"
    def capabilities(self) -> Capabilities: raise NotImplementedError
    def tier(self) -> Tier:
        c = self.capabilities()
        return Tier.ENFORCED if (c.areas or c.stayout) else (Tier.GATED if c.halt else Tier.ADVISORY)
    def sync_zones(self, file: Housefile) -> dict: raise NotImplementedError  # THS zone → native
    def relay(self, cmd: dict) -> dict: raise NotImplementedError
    def halt_all(self) -> dict:
        """E-stop path — implementations MUST NOT raise."""
        raise NotImplementedError
