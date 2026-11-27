from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

OnAlertPersist = Callable[..., int]
OnFrameGrab = Callable[[str], Awaitable[str | None]]


@dataclass
class Alert:
    kind: str  # stranger|dwell|leftover|rfid|door|ops|visitor_expiry
    space_id: str = ""
    title: str = ""
    severity: str = "warn"
    detail: dict[str, Any] = field(default_factory=dict)
    latch_key: str = ""  # 非空则同 key 锁存至窗口结束
    frame_path: str | None = None
    camera: str = ""


class AlertBus:
    """统一告警：同空间同类去抖；latch_key 锁存；限频落库。"""

    def __init__(
        self,
        store: Any,
        *,
        debounce_sec: float = 180.0,
        grab_frame: OnFrameGrab | None = None,
    ) -> None:
        self.store = store
        self.debounce_sec = max(30.0, debounce_sec)
        self.grab_frame = grab_frame
        self._last: dict[tuple[str, str], float] = {}
        self._latched: set[str] = set()

    def clear_latch(self, latch_key: str) -> None:
        self._latched.discard(latch_key)

    def clear_space_latches(self, space_id: str) -> None:
        dead = [k for k in self._latched if k.startswith(f"{space_id}:")]
        for k in dead:
            self._latched.discard(k)

    async def emit(self, alert: Alert) -> int | None:
        now = time.time()
        if alert.latch_key:
            if alert.latch_key in self._latched:
                return None
            self._latched.add(alert.latch_key)

        key = (alert.space_id or "_", alert.kind)
        last = self._last.get(key, 0.0)
        if not alert.latch_key and now - last < self.debounce_sec:
            return None
        self._last[key] = now

        frame = alert.frame_path
        if not frame and alert.camera and self.grab_frame:
            try:
                frame = await self.grab_frame(alert.camera)
            except Exception:
                _LOGGER.debug("alert frame grab failed", exc_info=True)

        try:
            return int(
                self.store.insert_alert(
                    space_id=alert.space_id,
                    kind=alert.kind,
                    severity=alert.severity,
                    title=alert.title or alert.kind,
                    detail=alert.detail,
                    frame_path=frame,
                    latch_key=alert.latch_key or None,
                )
            )
        except Exception:
            _LOGGER.exception("alert persist failed")
            return None
