"""THS-0004 — minimal sync bus. Handlers never crash the bus. Ledger sink: THS-0016."""
from __future__ import annotations
import logging
from collections import defaultdict
from typing import Callable
log = logging.getLogger("threshold.events")

class EventBus:
    def __init__(self):
        self._h: dict[str, list[Callable]] = defaultdict(list)
    def on(self, event_type: str, handler: Callable) -> None:
        self._h[event_type].append(handler); self._h["*"] = self._h["*"]
    def emit(self, event_type: str, payload: dict) -> None:
        for h in self._h.get(event_type, []) + self._h.get("*", []):
            try: h(event_type, payload)
            except Exception:  # noqa: BLE001 — bus survives everything
                log.exception("handler failed for %s", event_type)

BUS = EventBus()
