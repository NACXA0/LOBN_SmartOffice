"""放行策略：事件入口本身不开门；热路径决策后脉冲。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .audit import AuditLog
from .door import DoorController, DoorResult
from .hot_path import HotPathDecision, InMemoryHotPath
from .models import CctvEvent, GrantAck
from .notify import WeComNotifier

if TYPE_CHECKING:
    from .cloud_client import CloudClient

_LOGGER = logging.getLogger(__name__)

AckCallback = Callable[[GrantAck], Awaitable[None]]


@dataclass
class AccessPolicy:
    door: DoorController
    hot: InMemoryHotPath
    notify: WeComNotifier
    audit: AuditLog
    night_face_mode: str = "stricter"  # stricter | alert_only
    on_ack: AckCallback | None = None
    cloud: Any = None  # CloudClient | None；开门成功后上报里门状态
    room_id: int = 1
    # 云端站点配置：人脸仅在有效预约窗口内自动开门（可选便利）
    face_auto_open: bool = True
    require_grant_for_face: bool = True
    # 每扇门策略：gate/inner → {tap, sense, op, face_pulses, face_records_only, ...}
    door_policy: dict[str, Any] = field(default_factory=dict)
    face_target: str = "inner"  # 识别默认作用门
    _pending_face_grant: dict[str, float] = field(default_factory=dict)
    _unknown_cooldown: dict[str, float] = field(default_factory=dict)
    _close_report_task: asyncio.Task | None = field(default=None, repr=False)

    def apply_site_settings(self, settings: dict) -> None:
        if "face_auto_open" in settings:
            self.face_auto_open = bool(settings["face_auto_open"])
        policy = settings.get("door_policy") if isinstance(settings, dict) else None
        if isinstance(policy, dict):
            self.door_policy = {
                "gate": dict(policy.get("gate") or {}),
                "inner": dict(policy.get("inner") or {}),
            }
        else:
            # 兼容：仅全站 face_auto_open
            self.door_policy = {
                "gate": {
                    "exists": True,
                    "tap": True,
                    "sense": False,
                    "face_pulses": False,
                    "face_records_only": False,
                },
                "inner": {
                    "exists": True,
                    "tap": False,
                    "sense": bool(self.face_auto_open),
                    "face_pulses": bool(self.face_auto_open),
                    "face_records_only": False,
                },
            }
        # 识别默认门：优先里门有 sense，否则大门
        inner = self.door_policy.get("inner") or {}
        gate = self.door_policy.get("gate") or {}
        if inner.get("sense"):
            self.face_target = "inner"
        elif gate.get("sense"):
            self.face_target = "gate"
        else:
            self.face_target = "inner"
        # 合成旧开关：任一扇 face_pulses 为真才允许人脸脉冲路径
        self.face_auto_open = bool(gate.get("face_pulses") or inner.get("face_pulses"))

    def _door_cfg_for_face(self, event: CctvEvent) -> dict[str, Any]:
        raw = (event.payload or {}).get("door") or (event.payload or {}).get("target")
        tgt = raw if raw in ("gate", "inner") else self.face_target
        cfg = dict((self.door_policy or {}).get(tgt) or {})
        cfg["target"] = tgt
        return cfg

    async def on_cctv_event(self, event: CctvEvent) -> dict:
        """接收事实事件；决策开门。返回处理摘要。"""
        et = event.type
        if et == "face_unknown":
            return self._record_unknown(event)
        if et in ("zone_intrude", "loiter", "line_cross", "crowd"):
            self.notify.submit(f"[监控] {et} cam={event.cam_id}", level="warning")
            self.audit.append("alert", event_type=et, cam_id=event.cam_id, payload=event.payload)
            return {"action": "notify_only", "type": et}

        if et == "door_request_manual":
            return await self.manual_open(actor="cctv_panel")

        if et == "face_known":
            return await self._face_open(event)

        return {"action": "ignore", "type": et}

    def _record_unknown(self, event: CctvEvent) -> dict:
        """陌生人一律留痕；冷却避免刷爆审计。无论能否开门都统计。"""
        key = f"{event.cam_id}:{round(float(event.payload.get('similarity') or 0), 2)}"
        now = time.time()
        if now - self._unknown_cooldown.get(key, 0) < 30:
            return {"action": "unknown_coalesced", "type": "face_unknown"}
        self._unknown_cooldown[key] = now
        # 清理过期键，避免长期内存涨
        if len(self._unknown_cooldown) > 200:
            dead = [k for k, ts in self._unknown_cooldown.items() if now - ts > 600]
            for k in dead:
                self._unknown_cooldown.pop(k, None)
        self.notify.submit(f"[监控] face_unknown cam={event.cam_id}", level="warning")
        self.audit.append(
            "face_sighting",
            known=False,
            cam_id=event.cam_id,
            payload=event.payload,
            authorized=False,
        )
        return {"action": "recorded", "type": "face_unknown"}

    async def _face_open(self, event: CctvEvent) -> dict:
        if event.mode == "night" and self.night_face_mode == "alert_only":
            self.notify.submit(f"[夜间] 人脸命中仅告警 cam={event.cam_id}", level="info")
            self.audit.append("face_sighting", known=True, night_alert_only=True, payload=event.payload)
            return {"action": "night_alert_only"}

        person_id = event.payload.get("person_id")
        decision = self.hot.decide_face(person_id if isinstance(person_id, int) else None)
        if not decision.allow or decision.person is None:
            self.audit.append("face_denied", reason=decision.reason, payload=event.payload)
            self.audit.append(
                "face_sighting",
                known=False,
                reason=decision.reason,
                payload=event.payload,
                authorized=False,
            )
            return {"action": "denied", "reason": decision.reason}

        user_id = decision.person.user_id
        gd = self.hot.decide_user_grant(user_id) if user_id else HotPathDecision(False, "无用户")
        has_grant = bool(gd.allow and gd.grant)
        grant_id = gd.grant.grant_id if has_grant and gd.grant else None

        # 无论是否开门，已知人脸都记一笔出现
        self.audit.append(
            "face_sighting",
            known=True,
            person_id=decision.person.person_id,
            user_id=user_id,
            grant_id=grant_id,
            authorized=has_grant,
            payload=event.payload,
        )

        door_cfg = self._door_cfg_for_face(event)
        tgt = door_cfg.get("target") or self.face_target
        # AND：只记目击，不脉冲；只点按：不识别、不脉冲
        if door_cfg.get("face_records_only") or (
            door_cfg.get("sense") and door_cfg.get("tap") and door_cfg.get("op") == "and"
        ):
            if user_id and self.cloud is not None:
                try:
                    await self.cloud.push_door_sighting(user_id=user_id, target=tgt)
                except Exception:
                    _LOGGER.exception("上报门口目击失败")
            return {"action": "face_recorded_only", "reason": "and_mode_sighting", "target": tgt}

        face_pulses = bool(door_cfg.get("face_pulses"))
        if not face_pulses and not door_cfg.get("sense"):
            return {"action": "face_recorded_only", "reason": "sense_disabled", "target": tgt}
        if not face_pulses:
            # 兼容旧 face_auto_open=false
            if not self.face_auto_open:
                return {"action": "face_recorded_only", "reason": "face_auto_open_disabled"}
            return {"action": "face_recorded_only", "reason": "face_no_pulse", "target": tgt}

        if self.require_grant_for_face and not has_grant:
            self.audit.append("face_denied", reason="无有效预约授权", person_id=decision.person.person_id)
            return {"action": "denied", "reason": "无有效预约授权"}

        extra: list[str] = ["booking_grant"] if has_grant else []
        self.audit.append(
            "door_attempt",
            reason="face_match",
            person_id=decision.person.person_id,
            grant_id=grant_id,
            target=tgt,
        )
        result, command_id = await self.door.open(
            reason="face_match",
            person_id=decision.person.person_id,
            person_name=decision.person.name,
            user_id=user_id,
            grant_id=grant_id,
            extra_reasons=extra,
        )
        await self._after_open(result, command_id, grant_id, user_id)
        return {"action": result, "command_id": command_id, "target": tgt}

    async def open_by_grant(self, grant_id: str) -> dict:
        decision = self.hot.decide_grant(grant_id)
        if not decision.allow or decision.grant is None:
            self.audit.append("grant_denied", grant_id=grant_id, reason=decision.reason)
            if self.on_ack and decision.grant:
                await self.on_ack(
                    GrantAck(
                        grant_id=grant_id,
                        command_id="",
                        result="denied",
                        correlation_id=decision.grant.correlation_id,
                        ts=time.time(),
                        detail=decision.reason,
                    )
                )
            return {"action": "denied", "reason": decision.reason}

        grant = decision.grant
        self.audit.append("door_attempt", reason="booking_grant", grant_id=grant_id, user_id=grant.user_id)
        result, command_id = await self.door.open(
            reason="booking_grant",
            user_id=grant.user_id,
            grant_id=grant.grant_id,
            person_name=grant.user_id,
        )
        await self._after_open(result, command_id, grant.grant_id, grant.user_id, grant.correlation_id)
        return {"action": result, "command_id": command_id}

    async def manual_open(self, *, actor: str = "staff") -> dict:
        self.audit.append("door_attempt", reason="manual", actor=actor)
        result, command_id = await self.door.open(reason="manual", person_name=actor)
        self.notify.submit(f"[门禁] 手工开门 result={result} by={actor}", level="info")
        await self._report_inner_after_pulse(result)
        return {"action": result, "command_id": command_id}

    async def _report_inner_after_pulse(self, result: DoorResult) -> None:
        """脉冲成功：立即上报 open，open_seconds 后再上报 closed。

        door.py：ok→opened，否则 unknown（超时/失败未区分）。
        unknown 不假装 closed，也不报 fault。
        """
        cloud: CloudClient | None = self.cloud
        if cloud is None:
            return
        if result != "opened":
            # unknown：保持云端 unknown，不报 closed/fault
            return
        await cloud.report_door_status(self.room_id, inner_status="open")
        if self._close_report_task and not self._close_report_task.done():
            self._close_report_task.cancel()

        async def _close_later() -> None:
            try:
                await asyncio.sleep(float(self.door.open_seconds))
                await cloud.report_door_status(self.room_id, inner_status="closed")
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("上报里门 closed 失败")

        self._close_report_task = asyncio.create_task(_close_later())

    async def _after_open(
        self,
        result: DoorResult,
        command_id: str,
        grant_id: str | None,
        user_id: str | None,
        correlation_id: str = "",
    ) -> None:
        if result == "opened":
            self.notify.submit(f"[门禁] 已开门 cmd={command_id}", level="info")
        elif result == "unknown":
            self.notify.submit(f"[门禁] 结果未知 cmd={command_id}", level="warning")

        await self._report_inner_after_pulse(result)

        if grant_id and self.on_ack:
            first = result == "opened" and self.hot.mark_opened(grant_id)
            ack_result = result if result != "denied" else "denied"
            # 窗口内再次开门：不再发 opened 扣费回执
            if result == "opened" and not first:
                return
            if result == "denied":
                return
            await self.on_ack(
                GrantAck(
                    grant_id=grant_id,
                    command_id=command_id,
                    result=ack_result,  # type: ignore[arg-type]
                    correlation_id=correlation_id,
                    ts=time.time(),
                )
            )
