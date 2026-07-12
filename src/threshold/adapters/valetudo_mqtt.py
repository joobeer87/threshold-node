"""valetudo_mqtt adapter — STUB. Implement per KANBAN THS-0034 and docs/INTEGRATIONS.md.
Contract: base.BaseAdapter. Tier must come from capabilities()."""
from threshold.adapters.base import BaseAdapter, Capabilities

class Adapter(BaseAdapter):
    name = "valetudo_mqtt"
    def capabilities(self) -> Capabilities:
        raise NotImplementedError("THS-0034")
