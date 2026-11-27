from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from .alerts import Alert
from .backoff import ExpBackoff
from .detect.audio import AudioConfig, AudioDetector
from .detect.labels import default_audio_config, filter_detections
from .detect.motion import MotionDetector, parse_motion_config
from .detect.person import PersonDetector, count_persons, has_leftover
from .go2rtc import grab_jpeg_frames

_LOGGER = logging.getLogger(__name__)


class PresenceLoop:
    """1–2 fps 取帧 → 画面变动门槛 → 目标过滤；人数滑动窗口；滞留锁存告警。"""

    def __init__(
        self,
        store: Any,
        settings: Any,
        detector: PersonDetector,
        alerts: Any,
        arming: Any,
        env: Any,
        bus: Any,
        *,
        fps: float = 1.0,
        n_of_m: tuple[int, int] = (2, 3),
        alert_frames_dir: Path | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.detector = detector
        self.alerts = alerts
        self.arming = arming
        self.env = env
        self.bus = bus
        self.interval = 1.0 / max(0.5, min(2.0, fps))
        self.need, self.window = n_of_m
        self.alert_frames_dir = alert_frames_dir
        self._hits: dict[str, deque[bool]] = {}
        self._counts: dict[str, deque[float]] = {}
        self._backoff: dict[str, ExpBackoff] = {}
        self._motion: dict[str, MotionDetector] = {}
        self._audio: dict[str, AudioDetector] = {}
        self._leftover_done: set[str] = set()
        self._task: asyncio.Task | None = None
        self._door_state: dict[str, str] = {}

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _bo(self, cam: str) -> ExpBackoff:
        if cam not in self._backoff:
            self._backoff[cam] = ExpBackoff()
        return self._backoff[cam]

    async def _loop(self) -> None:
        await asyncio.sleep(8.0)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("presence tick failed")
            await asyncio.sleep(self.interval)

    async def tick(self) -> None:
        from PIL import Image
        import io

        for space in self.store.list_spaces():
            cam = space.get("camera") or ""
            if not cam:
                continue
            bo = self._bo(cam)
            if not bo.ready():
                continue
            try:
                frames = await grab_jpeg_frames(self.settings.go2rtc_url, cam, count=1)
            except Exception:
                bo.fail()
                await self.alerts.emit(
                    Alert(kind="ops", space_id=space["id"], title=f"取帧失败 {cam}", camera=cam)
                )
                continue
            if not frames:
                bo.fail()
                continue
            bo.success()
            # frames are already numpy BGR from go2rtc? check go2rtc
            frame = frames[0]
            if not isinstance(frame, np.ndarray):
                continue

            mm_pts = []
            for m in space.get("motion_masks") or []:
                pts = m.get("points") if isinstance(m, dict) else m
                if pts and len(pts) >= 3:
                    mm_pts.append(pts)

            mcfg = parse_motion_config(space.get("motion_cfg"))
            md = self._motion.setdefault(space["id"], MotionDetector())
            motion = md.process(frame, mcfg, motion_masks=mm_pts)

            # 音频：上游若注入 samples（测试/伴随进程）；配置开启时走 RMS 告警
            acfg_raw = space.get("audio_cfg") or default_audio_config()
            acfg = AudioConfig(
                enabled=bool(acfg_raw.get("enabled")),
                min_rms=float(acfg_raw.get("min_rms", 0.02)),
                cooldown_sec=float(acfg_raw.get("cooldown_sec", 30.0)),
            )
            if acfg.enabled:
                samples = space.get("_audio_samples")  # 可选注入；生产由 go2rtc 音频管线填充
                if samples:
                    ad = self._audio.setdefault(space["id"], AudioDetector())
                    ae = ad.process(samples, acfg)
                    if ae.triggered:
                        await self.alerts.emit(
                            Alert(
                                kind="audio",
                                space_id=space["id"],
                                title=f"{space.get('name') or space['id']} 异常声音",
                                camera=cam,
                                detail={"rms": round(ae.rms, 4)},
                            )
                        )

            zones = space.get("zones") or []
            poly = space.get("polygon") or []
            if zones and isinstance(zones[0], dict) and zones[0].get("points"):
                poly = zones[0]["points"]

            # 无画面变动且开启了运动门槛时，跳过重检测（省 CPU）；首帧校准除外
            if mcfg.enabled and not motion.moving and motion.skipped not in ("", "disabled"):
                continue
            if mcfg.enabled and not motion.moving and self._counts.get(space["id"]):
                # 静止：人数滑向 0，仍更新占用
                hist = self._counts.setdefault(space["id"], deque(maxlen=60))
                hist.append(0.0)
                continue

            raw_dets = self.detector.detect(frame, poly if poly else None)
            track = space.get("track_cfg") or {}
            obj_masks = []
            for m in space.get("object_masks") or []:
                pts = m.get("points") if isinstance(m, dict) else m
                if pts and len(pts) >= 3:
                    obj_masks.append(pts)
            dets = filter_detections(
                raw_dets,
                labels=list(track.get("labels") or ["person", "leftover"]),
                filters=track.get("filters") or {},
                object_masks=obj_masks,
            )
            # 区域：中心点需落在任一 zone（有 zone 时）
            if zones:
                from .detect.person import _point_in_poly

                zone_pts = [
                    z.get("points")
                    for z in zones
                    if isinstance(z, dict) and z.get("points") and len(z["points"]) >= 3
                ]
                if zone_pts:
                    kept = []
                    for d in dets:
                        x1, y1, x2, y2 = d.box
                        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                        if any(_point_in_poly(cx, cy, zp) for zp in zone_pts):
                            d.in_polygon = True
                            kept.append(d)
                    dets = kept

            persons = count_persons(dets)
            hits = self._hits.setdefault(space["id"], deque(maxlen=self.window))
            hits.append(persons > 0)
            stable = sum(1 for h in hits if h) >= self.need
            count = float(persons if stable else 0)
            hist = self._counts.setdefault(space["id"], deque(maxlen=60))
            hist.append(count)
            avg = sum(hist) / max(1, len(hist))
            peak = max(hist) if hist else 0.0
            self.store.set_space_person_count(space["id"], avg)
            await self.bus.publish(
                f"business/analytics/{space['id']}",
                {
                    "schema": "business.analytics.v1",
                    "avg": round(avg, 2),
                    "peak": float(peak),
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "window_min": max(1, int(len(hist) * self.interval / 60)),
                },
            )
            empty, why = self.arming.space_should_be_empty(space["id"])
            if empty and stable and count > 0:
                await self.alerts.emit(
                    Alert(
                        kind="dwell",
                        space_id=space["id"],
                        title=f"{space.get('name') or space['id']} 滞留",
                        latch_key=f"{space['id']}:dwell:{why}",
                        camera=cam,
                        detail={"reason": why, "count": count},
                    )
                )
            if empty and has_leftover(dets):
                lk = f"{space['id']}:leftover:{why}"
                if lk not in self._leftover_done:
                    self._leftover_done.add(lk)
                    await self.alerts.emit(
                        Alert(
                            kind="leftover",
                            space_id=space["id"],
                            title=f"{space.get('name') or space['id']} 遗留物",
                            latch_key=lk,
                            camera=cam,
                        )
                    )
            if not empty:
                # 清空该空间遗留锁存记录以便下次窗口
                self._leftover_done = {k for k in self._leftover_done if not k.startswith(f"{space['id']}:")}
                self.alerts.clear_space_latches(space["id"])

            intent = self.env.desired(
                occupied=stable and count > 0,
                armed=bool(space.get("armed")),
                has_window=bool(self.store.active_policy_windows(space_id=space["id"])),
            )
            await self.env.publish(space["id"], intent)

    async def on_door_state(self, node: str, state: str) -> None:
        prev = self._door_state.get(node)
        self._door_state[node] = state
        if prev == state:
            return
        if state != "open":
            return
        # 无 grant 而门开
        if not self.store.recent_grant_for_door(node, within_sec=45.0):
            space = self.store.get_space(node)
            armed = bool(space and space.get("armed"))
            await self.alerts.emit(
                Alert(
                    kind="door",
                    space_id=node,
                    title=f"门未授权打开 {node}",
                    severity="crit" if armed else "warn",
                    detail={"state": state, "armed": armed},
                )
            )

    async def on_rfid_event(self, payload: dict[str, Any]) -> None:
        event_id = str(payload.get("event_id") or "")
        if event_id and not self.store.mark_rfid_seen(event_id):
            return
        if payload.get("allowed") is True:
            return
        room = str(payload.get("room") or payload.get("gate") or "")
        tag = str(payload.get("tag_id") or "")
        asset = self.store.get_asset(tag) if tag else None
        name = (asset or {}).get("name") or tag
        await self.alerts.emit(
            Alert(
                kind="rfid",
                space_id=room,
                title=f"未授权资产 {name}",
                severity="crit",
                detail={"tag_id": tag, "asset": asset, "event_id": event_id},
                camera=(self.store.get_space(room) or {}).get("camera") or "",
            )
        )
