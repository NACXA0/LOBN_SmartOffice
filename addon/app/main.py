from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .access import AccessArbiter
from .ai_client import AiClient
from .alerts import Alert, AlertBus
from .api_office import router as office_router
from .arming import ArmingService
from .assets_svc import AssetService
from .auth import Actor, require_staff
from .backup import backup_loop
from .config import load_settings
from .detect.person import build_detector
from .environment import EnvironmentIntent
from .face.embedder import build_embedder
from .face.match import DoorMatcher, MatchConfig
from .face.session import SessionManager
from .go2rtc import grab_jpeg_frames
from .logging_setup import setup_logging
from .maintenance import maintenance_loop, refresh_disk_full, run_maintenance_once
from .mqtt_bus import MqttBus
from .policy import ScheduleAdapter
from .presence import PresenceLoop
from .store import GalleryStore

_LOGGER = logging.getLogger("smartoffice")

WEB = Path(__file__).resolve().parent / "webui"


async def _push_face_status(settings, user_id: str, store: GalleryStore, client: httpx.AsyncClient | None = None) -> None:
    """把本地 face_status 回写云端展示；失败不影响开门。"""
    base = (settings.cloud_base_url or "").rstrip("/")
    if not base or not settings.cloud_hmac_secret:
        return
    p = store.get_person(user_id)
    if not p:
        return
    own = client is None
    http = client or httpx.AsyncClient(timeout=5.0)
    try:
        await http.post(
            f"{base}/api/face/status/push",
            headers={"X-Lobn-Relay-Token": settings.cloud_hmac_secret},
            json={"user_id": int(user_id) if str(user_id).isdigit() else user_id, "face_status": p.face_status},
        )
    except Exception:
        _LOGGER.warning("cloud face_status push failed for %s", user_id)
    finally:
        if own:
            await http.aclose()


class StartBody(BaseModel):
    user_id: str
    display_name: str = ""
    channel: str = Field(default="staff", pattern="^(staff|student)$")


def _open_store(settings) -> GalleryStore:
    """库损坏时隔离旧文件另起新库（门可用性优先）。"""
    try:
        store = GalleryStore(settings.db_path)
        if getattr(store, "integrity_ok", True):
            return store
        store.close()
    except Exception:
        _LOGGER.exception("db open failed")
    bad = settings.db_path.with_suffix(settings.db_path.suffix + f".corrupt-{int(time.time())}")
    try:
        if settings.db_path.is_file():
            settings.db_path.rename(bad)
            _LOGGER.error("db corrupt; isolated to %s", bad)
    except Exception:
        _LOGGER.exception("db isolate failed")
    return GalleryStore(settings.db_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.frames_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "alert_frames").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "vlm_tmp").mkdir(parents=True, exist_ok=True)
    setup_logging(
        settings.data_dir,
        max_bytes=max(1, settings.log_max_mb) * 1024 * 1024,
        backup_count=max(1, settings.log_backup_count),
    )

    store = _open_store(settings)
    store.ensure_default_spaces(settings.door_node, list(settings.door_cameras))
    embedder = build_embedder(settings.embedder, settings.model_version)
    detector = build_detector(settings.detector)
    sessions = SessionManager(
        store,
        embedder,
        settings.frames_dir,
        needed=settings.required_enroll_frames,
    )
    matcher = DoorMatcher(
        store,
        embedder,
        MatchConfig(
            match_threshold=settings.match_threshold,
            verify_threshold=settings.verify_threshold,
            cooldown_sec=settings.cooldown_sec,
            required_match_frames=settings.required_match_frames,
            door_node=settings.door_node,
            door_cameras=list(settings.door_cameras),
            door_zones=list(settings.door_zones),
            sight_frames_dir=str(settings.data_dir / "sight_frames"),
        ),
    )
    bus = MqttBus(settings.mqtt_host, settings.mqtt_port, settings.mqtt_user, settings.mqtt_password)
    arbiter = AccessArbiter(store, bus, door_cooldown_sec=min(3.0, float(settings.cooldown_sec)))
    match_sem = asyncio.Semaphore(max(1, settings.match_concurrency))
    disk_flag: dict[str, Any] = {"disk_full": False}
    http = httpx.AsyncClient(timeout=8.0)
    ai = AiClient(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        per_minute=settings.ai_per_minute,
        per_day=settings.ai_per_day,
    )
    assets = AssetService(store, bus)
    arming = ArmingService(store, bus)
    env = EnvironmentIntent(bus)

    async def grab_alert_frame(camera: str) -> str | None:
        if disk_flag.get("disk_full"):
            return None
        frames = await grab_jpeg_frames(settings.go2rtc_url, camera, count=1)
        if not frames:
            return None
        from PIL import Image
        import io

        path = settings.data_dir / "alert_frames" / f"{int(time.time() * 1000)}_{camera}.jpg"
        rgb = frames[0][:, :, ::-1]
        Image.fromarray(rgb).save(path, format="JPEG", quality=75)
        return str(path)

    alerts = AlertBus(store, grab_frame=grab_alert_frame)
    presence = PresenceLoop(store, settings, detector, alerts, arming, env, bus)
    schedule = ScheduleAdapter(store, settings, arbiter, http)

    app.state.settings = settings
    app.state.store = store
    app.state.embedder = embedder
    app.state.detector = detector
    app.state.sessions = sessions
    app.state.matcher = matcher
    app.state.bus = bus
    app.state.arbiter = arbiter
    app.state.alerts = alerts
    app.state.assets = assets
    app.state.arming = arming
    app.state.ai = ai
    app.state.schedule = schedule
    app.state.disk_full = False
    app.state.http = http

    try:
        boot = run_maintenance_once(store, settings, sessions, matcher, full_frame_scan=True)
        _LOGGER.info("boot maintenance %s", boot)
    except Exception:
        _LOGGER.exception("boot maintenance failed")
    disk_flag["disk_full"] = refresh_disk_full(settings)
    app.state.disk_full = bool(disk_flag["disk_full"])

    async def on_mqtt(topic: str, payload: dict[str, Any]) -> None:
        if topic == "frigate/events":
            await on_frigate(payload)
            return
        if "/door/state" in topic:
            parts = topic.split("/")
            node = parts[1] if len(parts) > 1 else ""
            state = str(payload.get("state") or payload.get("raw") or "").lower()
            if node and state:
                await presence.on_door_state(node, state)
            return
        if "/rfid/event" in topic:
            await presence.on_rfid_event(payload)

    async def on_frigate(payload: dict[str, Any]) -> None:
        """过渡：仍订 frigate person；自有检测并行跑 presence。"""
        if not embedder.ready or disk_flag.get("disk_full"):
            return
        typ = payload.get("type")
        after = payload.get("after") or payload.get("before") or {}
        if typ not in ("new", "update"):
            return
        label = after.get("label") or ""
        if label != "person":
            return
        camera = after.get("camera") or ""
        zones = list(after.get("current_zones") or after.get("entered_zones") or [])
        event_id = after.get("id")
        ok, _why = matcher.should_handle(camera, zones, event_id)
        if not ok:
            return
        try:
            await asyncio.wait_for(match_sem.acquire(), timeout=0.001)
        except TimeoutError:
            return
        try:
            frames = await grab_jpeg_frames(settings.go2rtc_url, camera, count=settings.required_match_frames)
            if not frames:
                store.audit(None, camera, 0.0, "skip", {"reason": "go2rtc_empty"})
                return
            result = await asyncio.to_thread(matcher.match_frames, camera, frames, event_id)
            if result.user_id and result.decision in ("request", "deny"):
                await _push_face_status(settings, result.user_id, store, client=app.state.http)
            # 按摄像头所属空间决定门禁；无绑定时回退全局 door_node
            cam_space = store.find_space_by_camera(camera) or store.get_space(settings.door_node) or {}
            space_id = str(cam_space.get("id") or settings.door_node)
            access_mode = str(cam_space.get("access_mode") or "face")

            if result.decision == "request" and result.request:
                uid = result.request.user_id
                door = str(cam_space.get("door_node") or result.request.door or space_id)
                # 里门常开：识别与造访已在 match 内完成，这里只跳过 grant
                if access_mode == "always_open":
                    store.audit(
                        uid,
                        camera,
                        result.similarity,
                        "skip",
                        {"reason": "always_open", "space_id": space_id},
                    )
                    return
                if not store.person_allowed_in_space(uid, space_id) and not store.person_allowed_in_space(
                    uid, door
                ):
                    store.audit(uid, camera, result.similarity, "deny", {"reason": "space_restricted"})
                    await alerts.emit(
                        Alert(kind="stranger", space_id=space_id, title="访客不在允许空间", camera=camera)
                    )
                    return
                result.request.door = door
                await arbiter.apply(result.request)
            elif result.decision == "deny":
                title = "陌生人"
                if result.reason == "sighted_new":
                    title = "新面孔已建档"
                elif result.reason == "stranger":
                    title = "陌生人再次出现"
                elif result.user_id:
                    title = f"已识别·不可开门 ({result.reason})"
                await alerts.emit(
                    Alert(
                        kind="stranger",
                        space_id=space_id,
                        title=title,
                        camera=camera,
                        detail={
                            "similarity": result.similarity,
                            "reason": result.reason,
                            "user_id": result.user_id,
                            "access_mode": access_mode,
                        },
                    )
                )
            elif result.decision == "skip":
                if result.reason == "ignored":
                    pass  # 忽略名单：再识别但不告警（FaceID ignore list）
                else:
                    await alerts.emit(
                        Alert(
                            kind="ops",
                            space_id=settings.door_node,
                            title="看不清",
                            severity="info",
                            camera=camera,
                            detail={"reason": result.reason},
                        )
                    )
        finally:
            match_sem.release()

    await bus.start(on_mqtt)
    await arming.start()
    await presence.start()
    await schedule.start()

    backup_task = asyncio.create_task(backup_loop(store, settings.backup_dir, settings.backup_interval_hours))
    maint_task = asyncio.create_task(
        maintenance_loop(store, settings, sessions, matcher, disk_flag, settings.maintenance_interval_sec)
    )

    async def _sync_disk_flag() -> None:
        while True:
            try:
                app.state.disk_full = bool(disk_flag.get("disk_full"))
            except Exception:
                pass
            await asyncio.sleep(5.0)

    disk_task = asyncio.create_task(_sync_disk_flag())
    try:
        yield
    finally:
        for t in (backup_task, maint_task, disk_task):
            t.cancel()
        await schedule.stop()
        await presence.stop()
        await arming.stop()
        await bus.stop()
        try:
            await app.state.http.aclose()
        except Exception:
            pass
        store.close()


app = FastAPI(title="SmartOffice", version="0.4.0", lifespan=lifespan)
app.include_router(office_router)

# 本地「仅前端」静态页跨端口调 API 时需要 CORS（生产 Ingress 同域可忽略）
try:
    from fastapi.middleware.cors import CORSMiddleware

    _dev = __import__("os").environ.get("SMARTCENTER_DEV_AUTH", "").lower() in ("1", "true", "yes")
    if _dev:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
except Exception:
    pass

# Vite 构建产物：/assets/* ；旧静态兼容 /static/*
if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(WEB / "assets")), name="assets")
if WEB.is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/healthz")
async def healthz(request: Request) -> JSONResponse:
    emb = request.app.state.embedder
    bus = request.app.state.bus
    store: GalleryStore = request.app.state.store
    settings = request.app.state.settings
    try:
        request.app.state.disk_full = refresh_disk_full(settings)
    except Exception:
        pass
    code = 200 if emb.ready and not request.app.state.disk_full else 503
    body: dict[str, Any] = {
        "ok": emb.ready and not request.app.state.disk_full,
        "embedder_ready": emb.ready,
        "model_version": emb.model_version,
        "disk_full": request.app.state.disk_full,
        "mqtt_enabled": bus.enabled,
        "mqtt_host": bus.host if bus.enabled else "off",
    }
    try:
        body["store"] = store.stats()
        body["open_sessions"] = len(getattr(request.app.state.sessions, "_sessions", {}))
    except Exception:
        pass
    return JSONResponse(body, status_code=code)


def _person_item(p, store: GalleryStore | None = None) -> dict:
    item = {
        "user_id": p.user_id,
        "display_name": p.display_name,
        "face_status": p.face_status,
        "enabled": p.enabled,
        "verify_ok_count": p.verify_ok_count,
        "verify_fail_streak": p.verify_fail_streak,
        "updated_at": getattr(p, "updated_at", 0) or 0,
        "ha_person_entity": getattr(p, "ha_person_entity", "") or "",
        "person_kind": getattr(p, "person_kind", "staff") or "staff",
        "valid_until": getattr(p, "valid_until", None),
        "allowed_spaces": getattr(p, "allowed_spaces", "") or "",
        "origin": getattr(p, "origin", "office") or "office",
        "linked_user_id": getattr(p, "linked_user_id", "") or "",
        "first_seen_at": getattr(p, "first_seen_at", None),
        "last_seen_at": getattr(p, "last_seen_at", None),
        "visit_count": int(getattr(p, "visit_count", 0) or 0),
        "sighted": bool(getattr(p, "sighted", False)),
        "notes": getattr(p, "notes", "") or "",
        "phone": getattr(p, "phone", "") or "",
        "ignored": bool(getattr(p, "ignored", False)),
        "can_open": False,
        "has_thumb": False,
    }
    if store:
        photos = store.list_person_photos(p.user_id)
        item["has_thumb"] = any(ph.get("has_file") for ph in photos)
        item["frame_count"] = len(photos)
        item["can_open"] = store.can_open_by_face(p.user_id)
    return item


class CreatePersonBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    user_id: str = Field(default="", max_length=120)
    person_kind: str = "staff"  # staff|student|visitor
    notes: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=40)
    enabled: bool = True
    valid_until: float | None = None
    allowed_spaces: str = ""


@app.post("/api/persons")
async def create_person(
    body: CreatePersonBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    """手动建档：未识别过也可先录入信息，再上传人脸照片或现场采集。"""
    store = request.app.state.store
    try:
        p = store.create_person(
            user_id=body.user_id or None,
            display_name=body.display_name.strip(),
            person_kind=body.person_kind,
            origin="manual",
            notes=body.notes.strip(),
            phone=body.phone.strip(),
            enabled=body.enabled,
            valid_until=body.valid_until,
            allowed_spaces=body.allowed_spaces.strip(),
        )
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return _person_item(p, store)


@app.get("/api/persons")
async def persons(
    request: Request,
    q: str = "",
    scope: str = "all",
    actor: Actor = Depends(require_staff),
) -> dict:
    """人员=办公室里出现过的所有人（含陌生人）；scope=all|sighted|credential|stranger。
    credential=预约等平台录入了人脸但尚未被监控识别到的人。
    """
    store = request.app.state.store
    sc = scope if scope in ("all", "sighted", "credential", "stranger") else "all"
    rows = store.search_persons(q, scope=sc) if q.strip() else store.list_persons(scope=sc)
    return {"items": [_person_item(p, store) for p in rows], "scope": sc}


@app.get("/api/persons/search")
async def persons_search(
    request: Request,
    q: str = "",
    actor: Actor = Depends(require_staff),
) -> dict:
    """本地底库 + 可选云端反查，供采集页选人。"""
    store = request.app.state.store
    settings = request.app.state.settings
    local = [_person_item(p, store) for p in store.search_persons(q)]
    cloud: list[dict] = []
    base = (settings.cloud_base_url or "").rstrip("/")
    if q.strip() and base and settings.cloud_hmac_secret:
        try:
            r = await request.app.state.http.get(
                f"{base}/api/face/users/search",
                params={"q": q.strip(), "limit": 20},
                headers={"X-Lobn-Relay-Token": settings.cloud_hmac_secret},
            )
            if r.status_code < 400:
                cloud = list((r.json() or {}).get("items") or [])
        except Exception:
            _LOGGER.warning("cloud person search failed")
    # 合并：云端优先展示名，本地状态覆盖
    by_id: dict[str, dict] = {}
    for c in cloud:
        uid = str(c.get("user_id") or "")
        if not uid:
            continue
        by_id[uid] = {
            "user_id": uid,
            "display_name": c.get("display_name") or "",
            "face_status": c.get("face_status") or "none",
            "enabled": True,
            "source": "cloud",
            "has_thumb": False,
        }
    for p in local:
        uid = p["user_id"]
        if uid in by_id:
            by_id[uid].update({**p, "source": "both", "display_name": p["display_name"] or by_id[uid]["display_name"]})
        else:
            by_id[uid] = {**p, "source": "local"}
    items = list(by_id.values())
    # 纯数字且未命中：允许按 user_id 直接选
    if q.strip().isdigit() and q.strip() not in by_id:
        items.insert(
            0,
            {
                "user_id": q.strip(),
                "display_name": "",
                "face_status": "none",
                "enabled": True,
                "source": "manual",
                "has_thumb": False,
            },
        )
    return {"items": items[:40]}


@app.get("/api/stats")
async def stats_dashboard(request: Request, actor: Actor = Depends(require_staff)) -> dict:
    """概览页：底库分布、开门统计、待重采队列。"""
    store: GalleryStore = request.app.state.store
    bus = request.app.state.bus
    emb = request.app.state.embedder
    data = store.dashboard()
    data["runtime"] = {
        "embedder_ready": emb.ready,
        "model_version": emb.model_version,
        "mqtt_enabled": bus.enabled,
        "mqtt_host": bus.host if bus.enabled else "off",
        "disk_full": bool(request.app.state.disk_full),
        "open_sessions": len(getattr(request.app.state.sessions, "_sessions", {})),
        "ai_configured": bool(getattr(request.app.state.ai, "configured", False)),
        "db_ok": bool(getattr(store, "integrity_ok", True)),
    }
    data["overlapping_spaces"] = store.overlapping_policy_spaces()
    return data


@app.get("/api/persons/{user_id}")
async def person_detail(user_id: str, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    store = request.app.state.store
    p = store.get_person(user_id)
    if not p:
        raise HTTPException(404, "not_found")
    photos = store.list_person_photos(user_id)
    item = _person_item(p, store)
    item["photos"] = [
        {
            "id": ph["id"],
            "url": f"/api/persons/{user_id}/photos/{ph['id']}",
            "created_at": ph["created_at"],
            "has_file": ph["has_file"],
        }
        for ph in photos
    ]
    # 兼容旧 UI：按序帧
    item["frames"] = [
        {"index": i, "url": f"/api/persons/{user_id}/frame/{i}", "id": ph["id"]}
        for i, ph in enumerate(photos)
    ]
    item["visits"] = store.list_visits(user_id, limit=30)
    return item


class LinkBody(BaseModel):
    target_user_id: str = Field(min_length=1, max_length=120)


@app.post("/api/persons/{user_id}/link")
async def link_person(
    user_id: str,
    body: LinkBody,
    request: Request,
    actor: Actor = Depends(require_staff),
) -> dict:
    """把陌生人/重复档关联合并到已有身份（如预约平台 user_id）。"""
    store = request.app.state.store
    try:
        p = store.link_persons(user_id, body.target_user_id.strip())
    except KeyError:
        raise HTTPException(404, "not_found") from None
    return _person_item(p, store)


@app.get("/api/persons/{user_id}/visits")
async def person_visits(
    user_id: str, request: Request, limit: int = 40, actor: Actor = Depends(require_staff)
) -> dict:
    if not request.app.state.store.get_person(user_id):
        raise HTTPException(404, "not_found")
    return {"items": request.app.state.store.list_visits(user_id, limit=limit)}


@app.get("/api/persons/{user_id}/frame/{index}")
async def person_frame(user_id: str, index: int, request: Request, actor: Actor = Depends(require_staff)):
    paths = request.app.state.store.frame_paths_for_user(user_id)
    if index < 0 or index >= len(paths):
        raise HTTPException(404, "no_frame")
    path = Path(paths[index])
    if not path.is_file():
        raise HTTPException(404, "missing_file")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/persons/{user_id}/photos/{emb_id}")
async def person_photo_file(
    user_id: str, emb_id: int, request: Request, actor: Actor = Depends(require_staff)
):
    photos = request.app.state.store.list_person_photos(user_id)
    hit = next((p for p in photos if p["id"] == emb_id), None)
    if not hit or not hit.get("frame_path"):
        raise HTTPException(404, "no_frame")
    path = Path(hit["frame_path"])
    if not path.is_file():
        raise HTTPException(404, "missing_file")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/persons/{user_id}/photos")
async def upload_person_photos(
    user_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    actor: Actor = Depends(require_staff),
) -> dict:
    """相册入库：上传一张或多张人脸照片追加为参考图（借鉴 FaceID photo-library enrollment）。"""
    import io

    import numpy as np
    from PIL import Image

    from .face.quality import QualityConfig, evaluate_meta

    store = request.app.state.store
    emb = request.app.state.embedder
    if not store.get_person(user_id):
        raise HTTPException(404, "not_found")
    if request.app.state.disk_full:
        raise HTTPException(507, "disk_full")
    if not emb.ready:
        raise HTTPException(503, "model_not_loaded")

    # 相册照允许静态/略宽质检（不像门口防翻拍那么严）
    qcfg = QualityConfig(reject_gray=False, max_static_cosine=1.0)
    vecs: list = []
    paths: list[str | None] = []
    rejected: list[dict] = []
    out_dir = request.app.state.settings.data_dir / "gallery_photos" / user_id
    out_dir.mkdir(parents=True, exist_ok=True)

    for f in files[:12]:
        raw = await f.read()
        if not raw or len(raw) > 8_000_000:
            rejected.append({"name": f.filename, "reason": "too_large_or_empty"})
            continue
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            # 过大则缩小，省盘
            img.thumbnail((1280, 1280))
            bgr = np.asarray(img)[:, :, ::-1].copy()
        except Exception:
            rejected.append({"name": f.filename, "reason": "bad_image"})
            continue
        vec, meta = emb.embed(bgr)
        ok, reason = evaluate_meta(meta, qcfg)
        if not ok or vec is None:
            rejected.append({"name": f.filename, "reason": reason or "embed_fail"})
            continue
        dest = out_dir / f"{int(time.time() * 1000)}_{len(paths)}.jpg"
        img.save(dest, format="JPEG", quality=88)
        vecs.append(vec)
        paths.append(str(dest))

    if not vecs:
        raise HTTPException(400, detail={"reason": "no_valid_face", "rejected": rejected})

    try:
        stats = store.append_person_photos(
            user_id, emb.model_version, vecs, paths, max_photos=20
        )
    except KeyError:
        raise HTTPException(404, "not_found") from None
    p = store.get_person(user_id)
    return {
        "ok": True,
        **stats,
        "rejected": rejected,
        "person": _person_item(p, store),
    }


@app.delete("/api/persons/{user_id}/photos/{emb_id}")
async def delete_person_photo(
    user_id: str, emb_id: int, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    ok = request.app.state.store.delete_person_photo(user_id, emb_id)
    if not ok:
        raise HTTPException(404, "not_found")
    return {"ok": True, "id": emb_id}


class PersonPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    person_kind: str | None = None
    notes: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=40)
    ignored: bool | None = None
    enabled: bool | None = None
    valid_until: float | None = None
    set_valid_until: bool = False
    allowed_spaces: str | None = None


@app.patch("/api/persons/{user_id}")
async def patch_person(
    user_id: str,
    body: PersonPatchBody,
    request: Request,
    actor: Actor = Depends(require_staff),
) -> dict:
    store = request.app.state.store
    try:
        p = store.update_person(
            user_id,
            display_name=body.display_name.strip() if body.display_name is not None else None,
            person_kind=body.person_kind,
            notes=body.notes,
            phone=body.phone,
            ignored=body.ignored,
            enabled=body.enabled,
            valid_until=body.valid_until,
            set_valid_until=body.set_valid_until or body.valid_until is not None,
            allowed_spaces=body.allowed_spaces,
        )
    except KeyError:
        raise HTTPException(404, "not_found") from None
    return _person_item(p, store)


@app.post("/api/persons/{user_id}/disable")
async def disable_person(user_id: str, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    request.app.state.store.set_enabled(user_id, False)
    request.app.state.store.set_status(user_id, "rejected")
    request.app.state.store.clear_cooldown(user_id)
    return {"ok": True, "user_id": user_id, "enabled": False}


@app.post("/api/persons/{user_id}/enable")
async def enable_person(user_id: str, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    store = request.app.state.store
    p = store.get_person(user_id)
    if not p:
        raise HTTPException(404, "not_found")
    store.set_enabled(user_id, True)
    if p.face_status == "rejected":
        store.set_status(user_id, "accepted")
    return {"ok": True, "user_id": user_id, "enabled": True}


@app.delete("/api/persons/{user_id}")
async def delete_person(user_id: str, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    request.app.state.store.delete_person(user_id)
    return {"ok": True, "user_id": user_id}


@app.get("/api/persons/{user_id}/thumb")
async def person_thumb(user_id: str, request: Request, actor: Actor = Depends(require_staff)):
    paths = request.app.state.store.frame_paths_for_user(user_id)
    if not paths:
        raise HTTPException(404, "no_thumb")
    path = Path(paths[0])
    if not path.is_file():
        raise HTTPException(404, "missing_file")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/audit")
async def audit_list(
    request: Request,
    decision: str | None = None,
    result: str | None = None,
    source: str | None = None,
    limit: int = 50,
    actor: Actor = Depends(require_staff),
) -> dict:
    """跨来源开门流水（仲裁 ledger）。decision 兼容旧查询，映射到 result。"""
    res = result or decision
    if res == "deny":
        res = "drop"
    rows = request.app.state.store.list_access_ledger(
        limit=min(200, max(1, limit)),
        result=res or None,
        source=source or None,
    )
    return {"items": rows}


@app.get("/api/match-audit")
async def match_audit_list(
    request: Request,
    user_id: str | None = None,
    decision: str | None = None,
    limit: int = 50,
    actor: Actor = Depends(require_staff),
) -> dict:
    """人脸比对明细（相似度 / 拒因）。"""
    rows = request.app.state.store.list_audit(
        limit=min(200, max(1, limit)),
        decision=decision or None,
        user_id=user_id or None,
    )
    return {"items": rows}


class SyncBody(BaseModel):
    enabled: bool | None = None
    face_status: str | None = None
    display_name: str | None = None


@app.post("/api/persons/{user_id}/sync")
async def sync_person(
    user_id: str,
    body: SyncBody,
    request: Request,
    actor: Actor = Depends(require_staff),
) -> dict:
    """云端停用/状态同步：停用优先于本地旧状态。"""
    store = request.app.state.store
    p = store.get_person(user_id)
    name = body.display_name or (p.display_name if p else user_id)
    if body.enabled is False:
        store.set_enabled(user_id, False)
        store.set_status(user_id, body.face_status or "rejected")
        store.clear_cooldown(user_id)
        return {"ok": True, "user_id": user_id, "enabled": False, "face_status": body.face_status or "rejected"}
    if body.face_status:
        store.upsert_person(user_id, name, body.face_status, enabled=True if body.enabled is None else body.enabled)
    elif body.enabled is True:
        store.set_enabled(user_id, True)
    return {
        "ok": True,
        "user_id": user_id,
        "enabled": body.enabled,
        "face_status": body.face_status,
    }


@app.post("/api/admin/reembed")
async def reembed(request: Request, actor: Actor = Depends(require_staff)) -> dict:
    """换模型后用本地合格帧批量重嵌；不要求全员重采。"""
    if not actor.is_admin and actor.kind != "dev":
        raise HTTPException(403, "admin_required")
    store = request.app.state.store
    emb = request.app.state.embedder
    if not emb.ready:
        raise HTTPException(503, "model_not_loaded")
    from PIL import Image
    import io
    import numpy as np

    done, skipped = 0, 0
    for p in store.list_persons():
        paths = store.frame_paths_for_user(p.user_id)
        if not paths:
            skipped += 1
            continue
        vecs, kept = [], []
        for fp in paths:
            try:
                raw = Path(fp).read_bytes()
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                arr = np.asarray(img)[:, :, ::-1].copy()
                vec, meta = emb.embed(arr)
                if vec is None or not meta.get("ok"):
                    continue
                vecs.append(vec)
                kept.append(fp)
            except Exception:
                continue
        if not vecs:
            skipped += 1
            continue
        store.commit_enrollment(p.user_id, p.display_name, emb.model_version, vecs, kept)
        store.set_status(p.user_id, p.face_status if p.face_status in ("accepted", "verified") else "accepted")
        done += 1
    return {"ok": True, "reembedded": done, "skipped": skipped}


@app.post("/api/enroll/start")
async def enroll_start(
    body: StartBody,
    request: Request,
    actor: Actor = Depends(require_staff),
    x_lobn_user_id: str | None = Header(default=None, alias="X-Lobn-User-Id"),
) -> dict:
    request.app.state.disk_full = refresh_disk_full(request.app.state.settings)
    if request.app.state.disk_full:
        raise HTTPException(507, "disk_full")
    if not request.app.state.embedder.ready:
        raise HTTPException(503, "model_not_loaded")
    if body.channel == "staff" and actor.kind == "relay":
        raise HTTPException(403, "staff_channel_requires_ha")
    user_id = body.user_id
    if actor.kind == "relay":
        if not x_lobn_user_id:
            raise HTTPException(400, "relay_requires_user_id")
        if body.channel != "student":
            raise HTTPException(403, "relay_student_only")
        if str(body.user_id) != str(x_lobn_user_id):
            raise HTTPException(403, "user_mismatch")
        user_id = str(x_lobn_user_id)
    try:
        sess = request.app.state.sessions.start(user_id, body.display_name, body.channel, actor.id)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    return {
        "session_id": sess.session_id,
        "user_id": sess.user_id,
        "needed": sess.needed,
        "progress": 0,
    }


@app.post("/api/enroll/{session_id}/frame")
async def enroll_frame(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    actor: Actor = Depends(require_staff),
    x_lobn_user_id: str | None = Header(default=None, alias="X-Lobn-User-Id"),
) -> dict:
    if request.app.state.disk_full:
        raise HTTPException(507, "disk_full")
    data = await file.read()
    expected = None
    if actor.kind == "relay":
        expected = x_lobn_user_id
        if not expected:
            raise HTTPException(400, "relay_requires_user_id")
    result = request.app.state.sessions.push_jpeg(session_id, data, expected_user_id=expected)
    # 不回向量/阈值
    return {
        "ok": bool(result.get("ok")),
        "reason": result.get("reason"),
        "hint": result.get("hint"),
        "progress": result.get("progress"),
        "needed": result.get("needed"),
        "done": bool(result.get("done")),
        "face_status": result.get("face_status"),
    }


@app.post("/api/enroll/{session_id}/cancel")
async def enroll_cancel(session_id: str, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    request.app.state.sessions.cancel(session_id)
    return {"ok": True}


@app.post("/api/internal/match_test")
async def match_test(request: Request, actor: Actor = Depends(require_staff)) -> dict:
    """开发用：用上传的多帧跑门口仲裁（不经 MQTT）。"""
    form = await request.form()
    files = form.getlist("files")
    camera = str(form.get("camera") or "front_desk")
    frames = []
    from PIL import Image
    import io
    import numpy as np

    for f in files:
        raw = await f.read()  # type: ignore[attr-defined]
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        frames.append(np.asarray(img)[:, :, ::-1].copy())
    result = request.app.state.matcher.match_frames(camera, frames, event_id="test")
    out = {
        "decision": result.decision,
        "reason": result.reason,
        "user_id": result.user_id,
        "similarity": result.similarity,
    }
    if result.decision == "request" and result.request:
        arb = await request.app.state.arbiter.apply(result.request)
        out["arbiter"] = {"result": arb.result, "reason": arb.reason, "command_id": arb.command_id}
        if arb.grant and actor.is_admin:
            out["command_id"] = arb.grant.get("command_id")
    return out
