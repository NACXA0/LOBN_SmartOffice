from __future__ import annotations

import logging
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)


class AssetService:
    """台账 → retained allowlist；空名单须 force=True。"""

    def __init__(self, store: Any, bus: Any) -> None:
        self.store = store
        self.bus = bus

    def build_payload(self, room: str, tags: list[str], rev: int) -> dict[str, Any]:
        return {
            "schema": "home.rfid.allowlist.v1",
            "room": room,
            "tags": tags,
            "rev": rev,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    async def publish_allowlist(self, room: str, *, force_empty: bool = False) -> dict[str, Any]:
        tags = self.store.active_tags_for_room(room)
        if not tags and not force_empty:
            return {"ok": False, "reason": "empty_needs_force", "tags": [], "rev": self.store.get_allowlist_rev(room)}
        rev = self.store.next_allowlist_rev(room)
        payload = self.build_payload(room, tags, rev)
        ok = await self.bus.publish_retained(f"home/{room}/rfid/allowlist", payload)
        return {"ok": ok, "rev": rev, "tags": tags, "room": room}
