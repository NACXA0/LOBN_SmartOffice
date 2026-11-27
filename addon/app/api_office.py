from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from .access import AccessRequest
from .auth import Actor, require_staff

router = APIRouter(tags=["office"])


class SpaceBody(BaseModel):
    id: str = ""
    name: str = ""
    kind: str = Field(default="room", pattern="^(door|room|passage)$")
    camera: str = ""
    door_node: str = ""
    polygon: list[list[float]] | None = None


class PolygonBody(BaseModel):
    polygon: list[list[float]] = Field(default_factory=list)


class OpenBody(BaseModel):
    note: str = Field(default="", max_length=200)
    user_id: str = "staff"


class ArmBody(BaseModel):
    armed: bool | None = None
    override: bool | None = None
    schedule: list[dict[str, Any]] | None = None


class AssetBody(BaseModel):
    tag_id: str
    name: str = ""
    space_id: str = ""
    custodian: str = ""
    status: str = "active"


class AllowlistBody(BaseModel):
    room: str
    force_empty: bool = False


class VisitorBody(BaseModel):
    person_kind: str = Field(default="visitor", pattern="^(staff|student|visitor)$")
    valid_until: float | None = None
    allowed_spaces: str = ""


class ExplainBody(BaseModel):
    record_id: int
    kind: str = Field(default="match", pattern="^(match|alert)$")


class AssistBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: str = "default"


class VlmBody(BaseModel):
    alert_id: int


@router.get("/api/spaces")
async def list_spaces(request: Request, actor: Actor = Depends(require_staff)) -> dict:
    return {"items": request.app.state.store.list_spaces()}


@router.post("/api/spaces")
async def create_space(body: SpaceBody, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    if not actor.is_admin and actor.kind != "dev":
        raise HTTPException(403, "admin_required")
    space_id = (body.id or body.door_node or body.name or "").strip().replace(" ", "_")
    if not space_id:
        raise HTTPException(400, "id_required")
    item = request.app.state.store.upsert_space(
        space_id,
        name=body.name or space_id,
        kind=body.kind,
        camera=body.camera,
        door_node=body.door_node or (space_id if body.kind == "door" else ""),
        polygon=body.polygon,
    )
    return item


@router.get("/api/spaces/{space_id}")
async def space_detail(space_id: str, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    s = request.app.state.store.get_space(space_id)
    if not s:
        raise HTTPException(404, "not_found")
    s["windows"] = request.app.state.store.next_policy_windows(space_id=space_id, limit=5)
    s["arming_plan"] = request.app.state.store.get_arming_plan(space_id)
    s["alerts"] = request.app.state.store.list_alerts(limit=10, space_id=space_id, acked=False)
    return s


@router.patch("/api/spaces/{space_id}")
async def patch_space(
    space_id: str, body: SpaceBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    if not request.app.state.store.get_space(space_id):
        raise HTTPException(404, "not_found")
    return request.app.state.store.upsert_space(
        space_id,
        name=body.name,
        kind=body.kind,
        camera=body.camera,
        door_node=body.door_node,
        polygon=body.polygon,
    )


@router.put("/api/spaces/{space_id}/polygon")
async def set_polygon(
    space_id: str, body: PolygonBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    if not request.app.state.store.get_space(space_id):
        raise HTTPException(404, "not_found")
    request.app.state.store.set_space_polygon(space_id, body.polygon)
    return request.app.state.store.get_space(space_id) or {}


class RegionItem(BaseModel):
    id: str = ""
    name: str = ""
    points: list[list[float]] = Field(default_factory=list)


class RegionsBody(BaseModel):
    zones: list[RegionItem] | None = None
    motion_masks: list[RegionItem] | None = None
    object_masks: list[RegionItem] | None = None


class VisionCfgBody(BaseModel):
    motion_cfg: dict[str, Any] | None = None
    track_cfg: dict[str, Any] | None = None
    audio_cfg: dict[str, Any] | None = None


@router.put("/api/spaces/{space_id}/regions")
async def set_regions(
    space_id: str, body: RegionsBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    if not request.app.state.store.get_space(space_id):
        raise HTTPException(404, "not_found")

    def _dump(items: list[RegionItem] | None) -> list | None:
        if items is None:
            return None
        out = []
        for i, it in enumerate(items):
            out.append(
                {
                    "id": it.id or f"r{i+1}",
                    "name": it.name or it.id or f"区域{i+1}",
                    "points": it.points,
                }
            )
        return out

    try:
        return request.app.state.store.set_space_regions(
            space_id,
            zones=_dump(body.zones),
            motion_masks=_dump(body.motion_masks),
            object_masks=_dump(body.object_masks),
        )
    except KeyError:
        raise HTTPException(404, "not_found") from None


@router.patch("/api/spaces/{space_id}/vision")
async def patch_vision(
    space_id: str, body: VisionCfgBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    if not request.app.state.store.get_space(space_id):
        raise HTTPException(404, "not_found")
    try:
        return request.app.state.store.set_space_vision_cfg(
            space_id,
            motion_cfg=body.motion_cfg,
            track_cfg=body.track_cfg,
            audio_cfg=body.audio_cfg,
        )
    except KeyError:
        raise HTTPException(404, "not_found") from None


@router.get("/api/vision/labels")
async def vision_labels(actor: Actor = Depends(require_staff)) -> dict:
    from .detect.labels import COCO_LABELS, DEFAULT_TRACK_LABELS, LABEL_ZH, label_display

    return {
        "items": COCO_LABELS,
        "defaults": DEFAULT_TRACK_LABELS,
        "zh": {k: LABEL_ZH[k] for k in COCO_LABELS if k in LABEL_ZH},
        "catalog": [{"id": k, "zh": label_display(k)} for k in COCO_LABELS],
    }


@router.post("/api/spaces/{space_id}/open")
async def manual_open(
    space_id: str, body: OpenBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    space = request.app.state.store.get_space(space_id)
    door = (space or {}).get("door_node") or space_id
    req = AccessRequest(
        source="staff_manual",
        user_id=body.user_id or actor.id,
        display_name=actor.id,
        door=door,
        detail={"note": body.note, "actor": actor.id, "space_id": space_id},
    )
    result = await request.app.state.arbiter.apply(req)
    return {
        "ok": result.result == "grant",
        "result": result.result,
        "reason": result.reason,
        "command_id": result.command_id,
    }


@router.post("/api/spaces/{space_id}/arm")
async def set_arm(space_id: str, body: ArmBody, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    if not request.app.state.store.get_space(space_id):
        raise HTTPException(404, "not_found")
    if body.schedule is not None:
        request.app.state.store.set_arming_plan(space_id, body.schedule)
    if body.override is not None:
        request.app.state.store.set_space_armed(space_id, bool(body.override), override=bool(body.override))
    elif body.armed is not None:
        request.app.state.store.set_space_armed(space_id, body.armed)
    return request.app.state.store.get_space(space_id) or {}


@router.get("/api/spaces/{space_id}/preview.jpg")
async def space_preview(space_id: str, request: Request, actor: Actor = Depends(require_staff)):
    from fastapi.responses import Response

    space = request.app.state.store.get_space(space_id)
    if not space or not space.get("camera"):
        raise HTTPException(404, "no_camera")
    from .go2rtc import grab_jpeg_frames

    frames = await grab_jpeg_frames(request.app.state.settings.go2rtc_url, space["camera"], count=1)
    if not frames:
        raise HTTPException(503, "frame_unavailable")
    from PIL import Image
    import io

    rgb = frames[0][:, :, ::-1]
    img = Image.fromarray(rgb)
    bio = io.BytesIO()
    img.save(bio, format="JPEG", quality=80)
    return Response(bio.getvalue(), media_type="image/jpeg")


@router.get("/api/alerts")
async def list_alerts(
    request: Request,
    acked: bool | None = False,
    kind: str | None = None,
    space_id: str | None = None,
    limit: int = 50,
    actor: Actor = Depends(require_staff),
) -> dict:
    return {
        "items": request.app.state.store.list_alerts(
            limit=min(200, max(1, limit)),
            acked=acked,
            kind=kind,
            space_id=space_id,
        )
    }


@router.post("/api/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    ok = request.app.state.store.ack_alert(alert_id)
    if not ok:
        raise HTTPException(404, "not_found")
    return {"ok": True}


@router.get("/api/assets")
async def list_assets(request: Request, actor: Actor = Depends(require_staff)) -> dict:
    return {"items": request.app.state.store.list_assets()}


@router.post("/api/assets")
async def upsert_asset(body: AssetBody, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    return request.app.state.store.upsert_asset(
        body.tag_id.strip(),
        name=body.name,
        space_id=body.space_id,
        custodian=body.custodian,
        status=body.status,
    )


@router.delete("/api/assets/{tag_id}")
async def delete_asset(tag_id: str, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    request.app.state.store.delete_asset(tag_id)
    return {"ok": True}


@router.post("/api/assets/publish-allowlist")
async def publish_allowlist(
    body: AllowlistBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    """白名单只由此接口显式触发，不开放任意 MQTT 直发。"""
    if not actor.is_admin and actor.kind != "dev":
        raise HTTPException(403, "admin_required")
    result = await request.app.state.assets.publish_allowlist(body.room, force_empty=body.force_empty)
    if not result.get("ok") and result.get("reason") == "empty_needs_force":
        raise HTTPException(400, "empty_needs_force")
    return result


@router.get("/api/policy/windows")
async def policy_windows(
    request: Request, space_id: str | None = None, actor: Actor = Depends(require_staff)
) -> dict:
    return {
        "items": request.app.state.store.next_policy_windows(space_id=space_id, limit=30),
        "overlapping": request.app.state.store.overlapping_policy_spaces(),
    }


@router.post("/api/persons/{user_id}/visitor")
async def set_visitor(
    user_id: str, body: VisitorBody, request: Request, actor: Actor = Depends(require_staff)
) -> dict:
    if not request.app.state.store.get_person(user_id):
        raise HTTPException(404, "not_found")
    request.app.state.store.set_person_visitor(
        user_id,
        person_kind=body.person_kind,
        valid_until=body.valid_until,
        allowed_spaces=body.allowed_spaces,
    )
    p = request.app.state.store.get_person(user_id)
    return {
        "user_id": p.user_id,
        "person_kind": p.person_kind,
        "valid_until": p.valid_until,
        "allowed_spaces": p.allowed_spaces,
    }


@router.get("/api/ai/status")
async def ai_status(request: Request, actor: Actor = Depends(require_staff)) -> dict:
    ai = request.app.state.ai
    return {"configured": bool(ai and ai.configured), "model": getattr(ai, "model", "")}


class ExplainSpaceBody(BaseModel):
    space_id: str
    prompt: str = ""


@router.post("/api/ai/explain-space")
async def explain_space(body: ExplainSpaceBody, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    """对当前空间画面做一帧解释（不进开门热路径）。"""
    ai = request.app.state.ai
    if not ai or not ai.configured:
        raise HTTPException(503, "ai_not_configured")
    space = request.app.state.store.get_space(body.space_id)
    if not space or not space.get("camera"):
        raise HTTPException(404, "no_camera")
    from .go2rtc import grab_jpeg_frames
    from PIL import Image
    import io
    import time as _t

    frames = await grab_jpeg_frames(request.app.state.settings.go2rtc_url, space["camera"], count=1)
    if not frames:
        raise HTTPException(503, "frame_unavailable")
    tmp = request.app.state.settings.data_dir / "vlm_tmp" / f"space-{body.space_id}-{int(_t.time()*1000)}.jpg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frames[0][:, :, ::-1]).save(tmp, format="JPEG", quality=80)
    prompt = (body.prompt or "").strip() or (
        f"这是空间「{space.get('name') or body.space_id}」的当前画面。"
        "用一两句话说明有没有人、是否异常。不要建议开门或改布防。"
    )
    try:
        result = await ai.explain_image(request.app.state.http, tmp, prompt, session_id=actor.id)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    if result.get("status") == 429:
        raise HTTPException(429, "rate_limited")
    return result


@router.post("/api/ai/explain-crop")
async def explain_crop(body: ExplainBody, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    ai = request.app.state.ai
    if not ai or not ai.configured:
        raise HTTPException(503, "ai_not_configured")
    store = request.app.state.store
    path: Path | None = None
    if body.kind == "alert":
        alert = store.get_alert(body.record_id)
        if not alert:
            raise HTTPException(404, "not_found")
        if alert.get("frame_path"):
            path = Path(alert["frame_path"])
    else:
        rows = store.list_audit(limit=1)
        # match audit by id
        r = store._conn.execute("SELECT * FROM match_audit WHERE id=?", (body.record_id,)).fetchone()
        if not r:
            raise HTTPException(404, "not_found")
        detail = {}
        try:
            import json

            detail = json.loads(r["detail"] or "{}")
        except Exception:
            pass
        fp = detail.get("frame_path")
        if fp:
            path = Path(str(fp))
        # fallback: stranger 无帧时拒绝
    if not path or not path.is_file():
        raise HTTPException(404, "no_frame")
    result = await ai.explain_image(
        request.app.state.http,
        path,
        "这是门口抓到的一张脸。请判断是否正对镜头、光线/模糊是否可能导致比对失败。不要建议开门。",
        session_id=actor.id,
    )
    if result.get("status") == 429:
        raise HTTPException(429, "rate_limited")
    return result


@router.post("/api/ai/vlm")
async def vlm_alert(body: VlmBody, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    ai = request.app.state.ai
    if not ai or not ai.configured:
        raise HTTPException(503, "ai_not_configured")
    alert = request.app.state.store.get_alert(body.alert_id)
    if not alert:
        raise HTTPException(404, "not_found")
    path = Path(alert["frame_path"]) if alert.get("frame_path") else None
    if not path or not path.is_file():
        raise HTTPException(404, "no_frame")
    result = await ai.explain_image(
        request.app.state.http,
        path,
        f"这是告警「{alert.get('title')}」的画面。用一两句话说明可能发生了什么。不要建议开门或改布防。",
        session_id=actor.id,
    )
    if result.get("status") == 429:
        raise HTTPException(429, "rate_limited")
    return result


@router.post("/api/ai/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    actor: Actor = Depends(require_staff),
) -> dict:
    ai = request.app.state.ai
    if not ai or not ai.configured:
        raise HTTPException(503, "ai_not_configured")
    data = await file.read()
    if len(data) > 1_500_000:
        raise HTTPException(413, "audio_too_large")
    result = await ai.transcribe(request.app.state.http, data, session_id=actor.id)
    if result.get("status") == 429:
        raise HTTPException(429, "rate_limited")
    return result


@router.post("/api/ai/assist")
async def assist(body: AssistBody, request: Request, actor: Actor = Depends(require_staff)) -> dict:
    store = request.app.state.store
    office = store.dashboard().get("office") or {}
    spaces = store.list_spaces()
    alerts = store.list_alerts(limit=8, acked=False)
    windows = store.next_policy_windows(limit=5)
    lines = [
        f"待处理告警 {office.get('open_alerts', 0)}",
        f"有人空间 {office.get('occupied_spaces', 0)}",
        f"布防空间 {office.get('armed_spaces', 0)}",
        "空间: " + ", ".join(f"{s['id']}(人≈{s['person_count']:.1f},armed={s['armed']})" for s in spaces[:12]),
        "告警: " + "; ".join(f"{a['kind']}:{a['title']}" for a in alerts[:5]),
        "窗口: " + "; ".join(f"{w['space_id']} {w['subject_id']}" for w in windows[:5]),
    ]
    context = "\n".join(lines)
    ai = request.app.state.ai
    if not ai:
        return {"ok": True, "text": context, "mode": "local", "actions": _suggest_actions(alerts)}
    result = await ai.assist(
        request.app.state.http, body.question, context, session_id=body.session_id or actor.id
    )
    if result.get("status") == 429:
        raise HTTPException(429, "rate_limited")
    result["actions"] = _suggest_actions(alerts)
    return result


def _suggest_actions(alerts: list[dict]) -> list[dict[str, str]]:
    actions = []
    for a in alerts[:5]:
        if a["kind"] == "stranger":
            actions.append({"label": "去录入", "path": "/people"})
        actions.append({"label": "打开记录", "path": "/audit"})
    return actions


@router.get("/api/match-strangers")
async def match_strangers(request: Request, limit: int = 30, actor: Actor = Depends(require_staff)) -> dict:
    """熟人/陌生人/看不清归纳自 match_audit。"""
    rows = request.app.state.store.list_audit(limit=min(200, max(1, limit)))
    items = []
    for r in rows:
        dec = r.get("decision")
        detail = r.get("detail") or {}
        if dec == "request" or (dec == "grant"):
            bucket = "known"
        elif dec == "deny" or detail.get("reason") in ("no_match", "unknown"):
            bucket = "stranger"
        elif dec == "skip":
            bucket = "unclear"
        else:
            bucket = "unclear"
        items.append({**r, "bucket": bucket})
    return {"items": items}
