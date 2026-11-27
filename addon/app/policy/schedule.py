from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from ..access import AccessArbiter, AccessRequest
from ..backoff import ExpBackoff

_LOGGER = logging.getLogger(__name__)


class ScheduleAdapter:
    """FireClassroom pending grants → 总管策略窗口；过期只停本来源。"""

    def __init__(
        self,
        store: Any,
        settings: Any,
        arbiter: AccessArbiter,
        http: httpx.AsyncClient,
        *,
        pull_interval_sec: float = 60.0,
        open_lead_sec: float = 120.0,
    ) -> None:
        self.store = store
        self.settings = settings
        self.arbiter = arbiter
        self.http = http
        self.pull_interval_sec = max(30.0, pull_interval_sec)
        self.open_lead_sec = open_lead_sec
        self.backoff = ExpBackoff(base_sec=5.0, max_sec=120.0)
        self._opened: set[str] = set()
        self._task: asyncio.Task | None = None

    @property
    def configured(self) -> bool:
        return bool((self.settings.cloud_base_url or "").strip() and self.settings.cloud_hmac_secret)

    async def start(self) -> None:
        if not self.configured:
            _LOGGER.info("schedule adapter off (no cloud_base_url)")
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        await asyncio.sleep(3.0)
        while True:
            try:
                if self.backoff.ready():
                    await self.pull()
                    await self.maybe_open()
                    self.store.prune_policy_windows()
                    self.backoff.success()
            except asyncio.CancelledError:
                raise
            except Exception:
                delay = self.backoff.fail()
                _LOGGER.warning("schedule pull failed; backoff %.0fs", delay)
            await asyncio.sleep(self.pull_interval_sec)

    async def pull(self) -> int:
        base = (self.settings.cloud_base_url or "").rstrip("/")
        if not base:
            return 0
        r = await self.http.get(
            f"{base}/internal/grants/pending",
            params={"within_minutes": 120},
            headers={"X-Lobn-Relay-Token": self.settings.cloud_hmac_secret},
            timeout=10.0,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"pending_http_{r.status_code}")
        items = list((r.json() or {}).get("items") or [])
        n = 0
        for g in items:
            gid = str(g.get("grant_id") or "")
            if not gid:
                continue
            space = str(g.get("room_id") or self.settings.door_node)
            self.store.upsert_policy_window(
                gid,
                space_id=space,
                subject_id=str(g.get("user_id") or ""),
                subject_name="",
                source="booking",
                window_start=float(g.get("window_start") or 0),
                window_end=float(g.get("window_end") or 0),
                rev=str(g.get("correlation_id") or ""),
                raw=g,
            )
            n += 1
        return n

    async def maybe_open(self) -> None:
        now = time.time()
        for w in self.store.active_policy_windows():
            if w["id"] in self._opened:
                continue
            # 窗口内即可申请；lead 用于即将开始
            if w["window_start"] - self.open_lead_sec > now:
                continue
            req = AccessRequest(
                source="schedule",
                user_id=w["subject_id"] or "schedule",
                display_name=w["subject_name"] or w["subject_id"],
                door=w["space_id"],
                detail={"policy_id": w["id"], "source_adapter": "booking"},
            )
            result = await self.arbiter.apply(req)
            if result.result == "grant":
                self._opened.add(w["id"])
                await self._ack(w["id"], "opened", result.command_id or "")
            elif result.reason == "door_cooldown":
                continue

    async def _ack(self, grant_id: str, status: str, command_id: str) -> None:
        base = (self.settings.cloud_base_url or "").rstrip("/")
        if not base:
            return
        try:
            await self.http.post(
                f"{base}/internal/grants/{grant_id}/ack",
                headers={"X-Lobn-Relay-Token": self.settings.cloud_hmac_secret},
                json={"result": status, "command_id": command_id, "correlation_id": grant_id},
                timeout=10.0,
            )
        except Exception:
            _LOGGER.warning("schedule ack failed %s", grant_id)
