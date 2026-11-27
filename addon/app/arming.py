from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)


def schedule_armed_now(schedule: list, now: datetime | None = None) -> bool:
    """schedule: [{dow:0-6, start:'HH:MM', end:'HH:MM'}, ...]；空表表示不按表布防。"""
    if not schedule:
        return False
    now = now or datetime.now()
    dow = now.weekday()  # Mon=0
    hm = now.hour * 60 + now.minute
    for slot in schedule:
        try:
            if int(slot.get("dow", -1)) != dow:
                continue
            sh, sm = str(slot.get("start", "00:00")).split(":")
            eh, em = str(slot.get("end", "00:00")).split(":")
            start = int(sh) * 60 + int(sm)
            end = int(eh) * 60 + int(em)
            if start <= hm < end:
                return True
        except Exception:
            continue
    return False


class ArmingService:
    def __init__(self, store: Any, bus: Any) -> None:
        self.store = store
        self.bus = bus
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        await asyncio.sleep(5.0)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("arming tick failed")
            await asyncio.sleep(60.0)

    async def tick(self) -> None:
        for space in self.store.list_spaces():
            sid = space["id"]
            if space.get("arm_override") is not None:
                armed = bool(space["arm_override"])
            else:
                plan = self.store.get_arming_plan(sid)
                armed = schedule_armed_now(plan)
                if bool(space.get("armed")) != armed:
                    self.store.set_space_armed(sid, armed)
            await self.bus.publish_retained(
                f"business/security/arm/{sid}",
                {
                    "schema": "business.security.arm.v1",
                    "space": sid,
                    "armed": armed,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )

    def space_should_be_empty(self, space_id: str, *, grace_sec: float = 600.0) -> tuple[bool, str]:
        space = self.store.get_space(space_id)
        if space and space.get("armed"):
            return True, "armed"
        now = time.time()
        # 最近结束的窗口过宽限
        rows = self.store.next_policy_windows(space_id=space_id, limit=20)
        # next includes active; check ended windows via SQL would be better — use prune survivors
        # 简化：若无活跃窗口且 1h 内有已结束窗口，用 pulled 表
        active = self.store.active_policy_windows(space_id=space_id)
        if active:
            return False, ""
        # 查刚结束的
        cur = self.store._conn.execute(
            """
            SELECT id, window_end FROM policy_windows
            WHERE space_id=? AND window_end < ? AND window_end > ?
            ORDER BY window_end DESC LIMIT 1
            """,
            (space_id, now, now - 6 * 3600),
        ).fetchone()
        if cur and now > float(cur["window_end"]) + grace_sec:
            return True, f"window_ended:{cur['id']}"
        return False, ""
