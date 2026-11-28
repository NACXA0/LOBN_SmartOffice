from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Settings
    from .face.match import DoorMatcher
    from .face.session import SessionManager
    from .store import GalleryStore

_LOGGER = logging.getLogger(__name__)


def refresh_disk_full(settings: "Settings", min_free_mb: int = 64) -> bool:
    try:
        usage = shutil.disk_usage(str(settings.data_dir))
        return usage.free < max(16, min_free_mb) * 1024 * 1024
    except Exception:
        return False


def prune_orphan_frames(store: "GalleryStore", frames_dir: Path, *, full_scan: bool = False) -> int:
    """定点清理会话目录；全量 rglob 仅启动时一次。"""
    if not frames_dir.is_dir():
        return 0
    keep_raw = store.all_frame_paths()
    keep: set[str] = set()
    for k in keep_raw:
        keep.add(k)
        try:
            keep.add(str(Path(k).resolve()))
        except Exception:
            pass
        keep.add(Path(k).name)
    removed = 0
    # 会话半成品目录：enroll_frames/<session_id>/
    candidates: list[Path] = []
    if full_scan:
        candidates = list(frames_dir.rglob("*.jpg"))
    else:
        for child in frames_dir.iterdir():
            if child.is_dir():
                candidates.extend(child.glob("*.jpg"))
            elif child.suffix.lower() == ".jpg":
                candidates.append(child)
    for path in candidates:
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        if resolved in keep or str(path) in keep or path.name in keep:
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except Exception:
            continue
    if full_scan:
        for d in sorted((p for p in frames_dir.rglob("*") if p.is_dir()), reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass
    return removed


def prune_temp_media(dir_path: Path, *, max_age_hours: float = 24.0, max_files: int = 200) -> int:
    if not dir_path.is_dir():
        return 0
    cutoff = time.time() - max_age_hours * 3600.0
    files = sorted(dir_path.glob("*"), key=lambda p: p.stat().st_mtime if p.is_file() else 0)
    removed = 0
    for p in files:
        if not p.is_file():
            continue
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue
    files = [p for p in dir_path.glob("*") if p.is_file()]
    if len(files) > max_files:
        for p in sorted(files, key=lambda x: x.stat().st_mtime)[: len(files) - max_files]:
            try:
                p.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass
    return removed


def run_maintenance_once(
    store: "GalleryStore",
    settings: "Settings",
    sessions: "SessionManager | None" = None,
    matcher: "DoorMatcher | None" = None,
    *,
    full_frame_scan: bool = False,
) -> dict[str, Any]:
    """同步执行一轮容量收敛；供启动 + 周期任务调用。"""
    stats: dict[str, Any] = {}
    stats["audit"] = store.prune_audit(
        max_rows=settings.audit_max_rows,
        max_age_days=settings.audit_max_age_days,
    )
    stats["access_ledger"] = store.prune_access_ledger(
        max_rows=settings.audit_max_rows,
        max_age_days=settings.audit_max_age_days,
    )
    stats["alerts"] = store.prune_alerts(
        max_rows=settings.audit_max_rows,
        max_age_days=settings.audit_max_age_days,
    )
    stats["visits"] = store.prune_visits(
        max_rows=max(5000, settings.audit_max_rows),
        max_age_days=int(max(30, settings.audit_max_age_days)),
    )
    stats["grants"] = store.prune_grants_seen(max_age_hours=settings.grants_seen_max_age_hours)
    stats["rfid_seen"] = store.prune_rfid_seen(max_age_hours=settings.grants_seen_max_age_hours)
    stats["policy"] = store.prune_policy_windows()
    stats["visitors"] = store.expire_visitors()
    stats["cooldowns"] = store.prune_expired_cooldowns()
    if sessions is not None:
        stats["sessions"] = sessions.expire_stale(settings.session_ttl_sec)
    if matcher is not None:
        stats["events"] = matcher.prune_recent(max_age_sec=300.0)
    stats["orphan_frames"] = prune_orphan_frames(
        store, settings.frames_dir, full_scan=full_frame_scan
    )
    alert_dir = settings.data_dir / "alert_frames"
    vlm_dir = settings.data_dir / "vlm_tmp"
    stats["alert_frames"] = prune_temp_media(alert_dir)
    stats["vlm_tmp"] = prune_temp_media(vlm_dir, max_age_hours=6.0, max_files=50)
    deleted = (
        stats["audit"].get("deleted", 0)
        + stats["alerts"].get("deleted", 0)
        + stats["grants"]
        + stats["cooldowns"]
        + stats["orphan_frames"]
    )
    if deleted > 0:
        store.maybe_optimize()
    return stats


async def maintenance_loop(
    store: "GalleryStore",
    settings: "Settings",
    sessions: "SessionManager",
    matcher: "DoorMatcher",
    disk_flag: dict[str, Any],
    interval_sec: float | None = None,
) -> None:
    """长期运行守护：审计/去重表/会话/孤儿帧/磁盘水位。"""
    interval = interval_sec if interval_sec is not None else float(settings.maintenance_interval_sec)
    interval = max(60.0, interval)
    # 启动稍等再跑，避免与 backup 抢 IO
    await asyncio.sleep(15.0)
    while True:
        try:
            disk_flag["disk_full"] = refresh_disk_full(settings)
            stats = await asyncio.to_thread(run_maintenance_once, store, settings, sessions, matcher)
            _LOGGER.info(
                "maintenance ok audit=%s grants=%s cool=%s sess=%s orphans=%s disk_full=%s",
                stats.get("audit"),
                stats.get("grants"),
                stats.get("cooldowns"),
                stats.get("sessions"),
                stats.get("orphan_frames"),
                disk_flag.get("disk_full"),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("maintenance failed")
        await asyncio.sleep(interval)
