from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .embedder import Embedder, cosine
from .quality import QualityConfig, evaluate_meta
from ..access.arbiter import AccessRequest
from ..store import GalleryStore


@dataclass
class MatchConfig:
    match_threshold: float = 0.42
    verify_threshold: float = 0.48
    cooldown_sec: float = 30.0
    required_match_frames: int = 3
    door_node: str = "front_gate"
    door_cameras: list[str] = field(default_factory=list)
    door_zones: list[str] = field(default_factory=list)
    # 陌生人再识别略低于开门阈值，减少重复建档
    soft_match_threshold: float = 0.36
    sight_frames_dir: str = ""


@dataclass
class MatchResult:
    decision: str  # request | deny | skip
    reason: str
    user_id: str | None = None
    similarity: float = 0.0
    request: AccessRequest | None = None


class DoorMatcher:
    def __init__(
        self,
        store: GalleryStore,
        embedder: Embedder,
        cfg: MatchConfig,
        quality: QualityConfig | None = None,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.cfg = cfg
        self.quality = quality or QualityConfig()
        self._busy_cameras: set[str] = set()
        self._silent_until: dict[str, float] = {}
        self._recent_events: dict[str, float] = {}
        self._miss_streak: dict[str, int] = {}
        self._last_sight_create: dict[str, float] = {}

    def _event_key(self, camera: str, event_id: str | None) -> str:
        return f"{camera}:{event_id or ''}"

    def should_handle(self, camera: str, zones: list[str], event_id: str | None = None) -> tuple[bool, str]:
        if camera not in self.cfg.door_cameras:
            return False, "not_door_camera"
        if self.cfg.door_zones and not any(z in self.cfg.door_zones for z in zones):
            return False, "zone_miss"
        now = time.monotonic()
        if self._silent_until.get(camera, 0) > now:
            return False, "camera_silenced"
        if camera in self._busy_cameras:
            return False, "busy"
        ek = self._event_key(camera, event_id)
        last = self._recent_events.get(ek, 0)
        if event_id and now - last < 2.0:
            return False, "dedup"
        cam_last = self._recent_events.get(f"{camera}:*", 0)
        if now - cam_last < 1.0:
            return False, "dedup"
        return True, "ok"

    def _best_user(self, vec: np.ndarray, *, min_sim: float | None = None) -> tuple[str | None, float]:
        thr = self.cfg.match_threshold if min_sim is None else min_sim
        best_uid, best = None, -1.0
        for uid, vecs in self.store.memory_vectors().items():
            for g in vecs:
                s = cosine(vec, g)
                if s > best:
                    best, best_uid = s, uid
        if best_uid is None or best < thr:
            return None, float(best if best >= 0 else 0.0)
        return best_uid, float(best)

    def _save_sight_frame(self, frame_bgr: np.ndarray) -> str | None:
        root = Path(self.cfg.sight_frames_dir) if self.cfg.sight_frames_dir else self.store.db_path.parent / "sight_frames"
        try:
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"{uuid.uuid4().hex}.jpg"
            rgb = frame_bgr[:, :, ::-1] if frame_bgr.ndim == 3 else frame_bgr
            Image.fromarray(np.asarray(rgb, dtype=np.uint8)).save(path, format="JPEG", quality=85)
            return str(path)
        except Exception:
            return None

    def match_frames(self, camera: str, frames_bgr: list[np.ndarray], event_id: str | None = None) -> MatchResult:
        if not self.embedder.ready:
            return MatchResult("deny", "model_not_loaded")
        self._busy_cameras.add(camera)
        self._recent_events[f"{camera}:*"] = time.monotonic()
        if event_id:
            self._recent_events[self._event_key(camera, event_id)] = time.monotonic()
        try:
            per_frame: list[tuple[str, float]] = []
            embeds: list[tuple[np.ndarray, float, np.ndarray]] = []  # vec, sim, frame
            for img in frames_bgr:
                if img.ndim == 2 or (img.ndim == 3 and abs(float(img[..., 0].mean() - img[..., 2].mean())) < 1.5):
                    self.store.audit(None, camera, 0.0, "skip", {"reason": "infrared_or_gray"})
                    return MatchResult("skip", "infrared_or_gray")
                vec, meta = self.embedder.embed(img)
                ok_q, reason = evaluate_meta(meta, self.quality)
                if not ok_q or vec is None:
                    continue
                uid, sim = self._best_user(vec)
                if uid is None:
                    # 软匹配：关联已入库陌生人 / 略低相似的熟人
                    uid2, sim2 = self._best_user(vec, min_sim=self.cfg.soft_match_threshold)
                    if uid2 is not None:
                        per_frame.append((uid2, sim2))
                        embeds.append((vec, sim2, img))
                    else:
                        per_frame.append(("?", sim))
                        embeds.append((vec, sim, img))
                else:
                    p = self.store.get_person(uid)
                    if not p or not p.enabled:
                        per_frame.append(("?", sim))
                        embeds.append((vec, sim, img))
                    else:
                        per_frame.append((uid, sim))
                        embeds.append((vec, sim, img))

            if len(per_frame) < self.cfg.required_match_frames:
                self._miss_streak[camera] = self._miss_streak.get(camera, 0) + 1
                if self._miss_streak[camera] >= 5:
                    self._silent_until[camera] = time.monotonic() + min(60.0, 5.0 * self._miss_streak[camera])
                self.store.audit(None, camera, 0.0, "deny", {"reason": "not_enough_frames", "n": len(per_frame)})
                return MatchResult("deny", "not_enough_frames")

            # 未知：建档入库（全员记录）
            if any(u == "?" for u, _ in per_frame):
                return self._handle_unknown(camera, embeds)

            ids = {u for u, _ in per_frame}
            main = per_frame[0][0]
            if any(u != main for u, _ in per_frame):
                self.store.audit(None, camera, 0.0, "deny", {"reason": "multi_identity", "ids": list(ids)})
                return MatchResult("deny", "multi_identity")

            sims = [s for u, s in per_frame if u == main]
            avg_sim = float(sum(sims) / len(sims))
            if self.store.cooldown_active(main, time.monotonic()):
                self.store.audit(main, camera, avg_sim, "skip", {"reason": "cooldown"})
                self.store.record_visit(
                    main, camera=camera, space_id=self.cfg.door_node, kind="sight", similarity=avg_sim, min_interval_sec=60
                )
                return MatchResult("skip", "cooldown", user_id=main, similarity=avg_sim)

            # 造访事实：匹配到谁都记
            self.store.record_visit(
                main,
                camera=camera,
                space_id=self.cfg.door_node,
                kind="match",
                similarity=avg_sim,
            )

            person = self.store.get_person(main)
            if person and person.ignored:
                self.store.audit(main, camera, avg_sim, "skip", {"reason": "ignored"})
                return MatchResult("skip", "ignored", user_id=main, similarity=avg_sim)

            if not self.store.can_open_by_face(main):
                reason = "stranger" if person and person.person_kind == "stranger" else "not_door_eligible"
                self.store.audit(main, camera, avg_sim, "deny", {"reason": reason, "kind": getattr(person, "person_kind", "")})
                return MatchResult("deny", reason, user_id=main, similarity=avg_sim)

            verify_ok = avg_sim >= self.cfg.verify_threshold
            new_status = self.store.bump_verify(main, verify_ok)
            if new_status == "pending":
                self.store.audit(main, camera, avg_sim, "deny", {"reason": "recollect_required"})
                return MatchResult("deny", "recollect_required", user_id=main, similarity=avg_sim)

            until_mono = time.monotonic() + self.cfg.cooldown_sec
            self.store.set_cooldown(main, until_mono, time.time() + self.cfg.cooldown_sec)
            self._miss_streak[camera] = 0

            person = self.store.get_person(main)
            req = AccessRequest(
                source="face_match",
                user_id=main,
                display_name=person.display_name if person else main,
                door=self.cfg.door_node,
                similarity=avg_sim,
                camera=camera,
                frigate_event_id=event_id,
                detail={"status": new_status},
            )
            self.store.audit(main, camera, avg_sim, "request", {"status": new_status})
            return MatchResult("request", "face_match", user_id=main, similarity=avg_sim, request=req)
        finally:
            self._busy_cameras.discard(camera)

    def _handle_unknown(
        self, camera: str, embeds: list[tuple[np.ndarray, float, np.ndarray]]
    ) -> MatchResult:
        """未匹配：入库陌生人 + 人脸 + 造访；短时同摄像头去抖避免刷爆。"""
        now = time.monotonic()
        last = self._last_sight_create.get(camera, 0.0)
        if embeds and now - last < 45.0:
            # 去抖窗口内：尝试软关联最近陌生人
            vec, sim, frame = max(embeds, key=lambda x: x[1])
            uid, soft = self._best_user(vec, min_sim=self.cfg.soft_match_threshold)
            if uid:
                self.store.record_visit(
                    uid, camera=camera, space_id=self.cfg.door_node, kind="sight", similarity=soft
                )
                self.store.audit(uid, camera, soft, "deny", {"reason": "stranger_resight"})
                return MatchResult("deny", "stranger", user_id=uid, similarity=soft)
            self.store.audit(None, camera, float(sim), "deny", {"reason": "unknown_in_frame", "dedup": True})
            return MatchResult("deny", "unknown_in_frame")

        if not embeds:
            self.store.audit(None, camera, 0.0, "deny", {"reason": "unknown_in_frame"})
            return MatchResult("deny", "unknown_in_frame")

        vec, sim, frame = max(embeds, key=lambda x: x[1])
        path = self._save_sight_frame(frame)
        person = self.store.ingest_sighting(
            vec,
            model_version=self.embedder.model_version,
            frame_path=path,
            camera=camera,
            space_id=self.cfg.door_node,
            similarity=float(sim),
        )
        self._last_sight_create[camera] = now
        self.store.audit(
            person.user_id,
            camera,
            float(sim),
            "deny",
            {"reason": "sighted_new", "person_kind": "stranger"},
        )
        return MatchResult("deny", "sighted_new", user_id=person.user_id, similarity=float(sim))

    def prune_recent(self, max_age_sec: float = 300.0) -> int:
        """清理事件去重表，避免 Frigate event_id 长期堆积。"""
        now = time.monotonic()
        cutoff = now - max(30.0, max_age_sec)
        dead = [k for k, ts in self._recent_events.items() if ts < cutoff]
        for k in dead:
            self._recent_events.pop(k, None)
        for cam, until in list(self._silent_until.items()):
            if until < now:
                self._silent_until.pop(cam, None)
                self._miss_streak.pop(cam, None)
        return len(dead)
