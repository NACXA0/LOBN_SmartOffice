from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..mqtt_bus import MqttBus
from ..store import GalleryStore

_LOGGER = logging.getLogger(__name__)


@dataclass
class AccessRequest:
    """模块产出的开门申请，不上总线。"""

    source: str  # face_match | schedule | …
    user_id: str
    display_name: str = ""
    door: str = "front_gate"
    similarity: float = 0.0
    camera: str = ""
    frigate_event_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArbiterResult:
    result: str  # grant | drop
    reason: str
    command_id: str | None = None
    grant: dict[str, Any] | None = None


class AccessArbiter:
    """唯一调用 publish_grant；按门冷却；发布成功才记门冷却。"""

    def __init__(
        self,
        store: GalleryStore,
        bus: MqttBus,
        *,
        door_cooldown_sec: float = 3.0,
        grant_ttl_sec: int = 3,
        grant_expire_sec: int = 15,
    ) -> None:
        self.store = store
        self.bus = bus
        self.door_cooldown_sec = max(0.0, door_cooldown_sec)
        self.grant_ttl_sec = grant_ttl_sec
        self.grant_expire_sec = grant_expire_sec

    async def apply(self, req: AccessRequest) -> ArbiterResult:
        door = (req.door or "front_gate").strip() or "front_gate"
        now_mono = time.monotonic()
        if self.store.door_cooldown_active(door, now_mono):
            self.store.log_access(
                source=req.source,
                door=door,
                user_id=req.user_id,
                display_name=req.display_name,
                result="drop",
                reason="door_cooldown",
                detail={**req.detail, "camera": req.camera},
            )
            return ArbiterResult("drop", "door_cooldown")

        command_id = uuid.uuid4().hex
        now = time.time()
        grant = {
            "schema": "business.access.grant.v1",
            "node": door,
            "door": door,
            "ttl_sec": self.grant_ttl_sec,
            "reason": req.source,
            "subject": {
                "user_id": req.user_id,
                "display_name": req.display_name or req.user_id,
            },
            "frigate_event_id": req.frigate_event_id,
            "command_id": command_id,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + self.grant_expire_sec)),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        }

        try:
            ok = await self.bus.publish_grant(grant)
        except Exception:
            _LOGGER.exception("publish_grant failed %s", command_id)
            self.store.log_access(
                source=req.source,
                door=door,
                user_id=req.user_id,
                display_name=req.display_name,
                result="drop",
                reason="publish_failed",
                command_id=command_id,
                detail=req.detail,
            )
            return ArbiterResult("drop", "publish_failed", command_id=command_id)

        if not ok:
            # 断连只丢不积压；门走保命按钮
            self.store.log_access(
                source=req.source,
                door=door,
                user_id=req.user_id,
                display_name=req.display_name,
                result="drop",
                reason="mqtt_unavailable",
                command_id=command_id,
                detail=req.detail,
            )
            return ArbiterResult("drop", "mqtt_unavailable", command_id=command_id)

        until_mono = now_mono + self.door_cooldown_sec
        until_wall = now + self.door_cooldown_sec
        detail = {**req.detail, "camera": req.camera, "similarity": req.similarity}
        if not self.store.commit_grant_success(
            command_id=command_id,
            door=door,
            until_mono=until_mono,
            until_wall=until_wall,
            source=req.source,
            user_id=req.user_id,
            display_name=req.display_name,
            reason=req.source,
            detail=detail,
        ):
            self.store.log_access(
                source=req.source,
                door=door,
                user_id=req.user_id,
                display_name=req.display_name,
                result="drop",
                reason="duplicate_command",
                command_id=command_id,
                detail=req.detail,
            )
            return ArbiterResult("drop", "duplicate_command", command_id=command_id)
        return ArbiterResult("grant", req.source, command_id=command_id, grant=grant)
