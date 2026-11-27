from __future__ import annotations

import logging
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)


class EnvironmentIntent:
    """占用/窗口/布防 → 环境意图；迟滞 + 最短保持，只发变化。"""

    def __init__(self, bus: Any, *, hold_sec: float = 180.0) -> None:
        self.bus = bus
        self.hold_sec = hold_sec
        self._last: dict[str, tuple[dict, float]] = {}

    def desired(self, *, occupied: bool, armed: bool, has_window: bool) -> dict[str, Any]:
        if armed and not occupied:
            return {"lights": "off", "hvac": "eco", "fresh_air": "off"}
        if occupied or has_window:
            return {"lights": "on", "hvac": "comfort", "fresh_air": "on"}
        return {"lights": "off", "hvac": "eco", "fresh_air": "off"}

    async def publish(self, space_id: str, intent: dict[str, Any]) -> bool:
        now = time.time()
        prev = self._last.get(space_id)
        if prev:
            old, ts = prev
            if old == intent:
                return False
            if now - ts < self.hold_sec:
                return False
        self._last[space_id] = (dict(intent), now)
        return await self.bus.publish(
            f"business/environment/{space_id}",
            {
                "schema": "business.environment.v1",
                "space": space_id,
                "intent": intent,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
