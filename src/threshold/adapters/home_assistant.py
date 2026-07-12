"""home_assistant adapter — STUB. Implement per KANBAN THS-0030 and docs/INTEGRATIONS.md.
Contract: base.BaseAdapter. Tier must come from capabilities()."""
from threshold.adapters.base import BaseAdapter, Capabilities

class Adapter(BaseAdapter):
    name = "home_assistant"
    def capabilities(self) -> Capabilities:
        raise NotImplementedError("THS-0030")
