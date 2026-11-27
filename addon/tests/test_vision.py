from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.detect.audio import AudioConfig, AudioDetector
from app.detect.labels import filter_detections, label_display
from app.detect.motion import MotionConfig, MotionDetector
from app.detect.person import Detection, HogPersonDetector, MockDetector, build_detector, _HAS_CV2
from app.store import GalleryStore


def _blank(h=120, w=160, color=40) -> np.ndarray:
    return np.full((h, w, 3), color, dtype=np.uint8)


def _with_blob(frame: np.ndarray, x0=40, y0=30, x1=80, y1=70, color=220) -> np.ndarray:
    out = frame.copy()
    out[y0:y1, x0:x1] = color
    return out


def test_motion_detects_blob_and_mask_blocks_it():
    md = MotionDetector()
    cfg = MotionConfig(enabled=True, threshold=25, contour_area=20, lightning_threshold=0.95, bg_alpha=0.01)
    bg = _blank()
    assert md.process(bg, cfg).moving is False
    moving = _with_blob(bg)
    r1 = md.process(moving, cfg)
    assert r1.moving is True
    assert r1.area >= 20

    md2 = MotionDetector()
    md2.process(bg, cfg)
    # 遮罩盖住 blob（OSD 场景）
    mask = [[0.2, 0.2], [0.6, 0.2], [0.6, 0.7], [0.2, 0.7]]
    r2 = md2.process(moving, cfg, motion_masks=[mask])
    assert r2.moving is False


def test_motion_lightning_skip():
    md = MotionDetector()
    cfg = MotionConfig(enabled=True, threshold=10, contour_area=1, lightning_threshold=0.3)
    md.process(_blank(color=0), cfg)
    r = md.process(_blank(color=255), cfg)
    assert r.skipped == "lightning"
    assert r.moving is False


def test_motion_recalibrate_on_frame_skip():
    md = MotionDetector()
    cfg = MotionConfig(
        enabled=True,
        threshold=10,
        contour_area=1,
        lightning_threshold=0.99,
        frame_skip_threshold=0.5,
    )
    md.process(_blank(color=0), cfg)
    r = md.process(_blank(color=255), cfg)
    assert r.skipped == "recalibrate"
    assert r.moving is False


def test_motion_disabled():
    md = MotionDetector()
    cfg = MotionConfig(enabled=False)
    r = md.process(_with_blob(_blank()), cfg)
    assert r.skipped == "disabled"
    assert r.moving is False


def test_object_mask_and_label_filter():
    dets = [
        Detection("person", 0.9, (0.1, 0.1, 0.3, 0.5)),
        Detection("cup", 0.9, (0.6, 0.6, 0.7, 0.8)),
        Detection("person", 0.2, (0.4, 0.4, 0.5, 0.5)),
    ]
    masks = [[[0.0, 0.0], [0.4, 0.0], [0.4, 0.4], [0.0, 0.4]]]
    out = filter_detections(
        dets,
        labels=["person"],
        filters={"person": {"min_score": 0.5, "min_area": 0.001}},
        object_masks=masks,
    )
    assert out == []


def test_label_filter_keeps_valid_person():
    dets = [Detection("person", 0.9, (0.2, 0.2, 0.5, 0.8))]
    out = filter_detections(
        dets,
        labels=["person"],
        filters={"person": {"min_score": 0.5, "min_area": 0.01}},
        object_masks=[],
    )
    assert len(out) == 1
    assert out[0].label == "person"


def test_label_display_zh():
    assert label_display("person") == "人"
    assert label_display("leftover") == "遗留物"


def test_audio_rms_trigger_and_cooldown():
    ad = AudioDetector()
    cfg = AudioConfig(enabled=True, min_rms=0.05, cooldown_sec=60)
    quiet = [0.001] * 1000
    loud = [0.2] * 1000
    assert ad.process(quiet, cfg).triggered is False
    assert ad.process(loud, cfg).triggered is True
    assert ad.process(loud, cfg).reason == "cooldown"


def test_space_regions_persist(tmp_path):
    store = GalleryStore(tmp_path / "v.sqlite3")
    store.ensure_default_spaces("front_gate", ["cam"])
    store.set_space_regions(
        "front_gate",
        zones=[{"id": "z1", "name": "门前", "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]}],
        motion_masks=[{"id": "m1", "name": "OSD", "points": [[0.7, 0.0], [1.0, 0.0], [1.0, 0.15], [0.7, 0.15]]}],
        object_masks=[],
    )
    store.set_space_vision_cfg(
        "front_gate",
        motion_cfg={"threshold": 40, "enabled": True, "frame_skip_threshold": 0.6},
        track_cfg={"labels": ["person", "backpack"], "filters": {"person": {"min_score": 0.6}}},
        audio_cfg={"enabled": True, "min_rms": 0.03},
    )
    s = store.get_space("front_gate")
    assert s["zones"][0]["name"] == "门前"
    assert s["motion_masks"][0]["name"] == "OSD"
    assert s["motion_cfg"]["threshold"] == 40
    assert s["motion_cfg"]["frame_skip_threshold"] == 0.6
    assert "backpack" in s["track_cfg"]["labels"]
    assert s["track_cfg"]["filters"]["person"]["min_score"] == 0.6
    assert s["audio_cfg"]["enabled"] is True
    assert len(s["polygon"]) == 3


def test_build_detector_hog_or_mock():
    d = build_detector("mock")
    assert isinstance(d, MockDetector)
    if _HAS_CV2:
        h = build_detector("hog")
        assert isinstance(h, HogPersonDetector)
        # 空/小帧不崩
        assert h.detect(_blank(32, 32)) == []
        assert h.detect(_blank(240, 320)) == []  # 纯色无行人


def test_opencv_available_for_motion():
    """运动检测优先走 OpenCV 轮廓路径。"""
    assert _HAS_CV2 is True


def _video_devices() -> list[str]:
    return sorted(str(p) for p in Path("/dev").glob("video*") if p.exists())


@pytest.mark.skipif(not _video_devices(), reason="本机无 /dev/video*；合成帧已覆盖算法")
def test_local_camera_optional_motion():
    """可选：本机摄像头 → OpenCV 取帧 → 运动检测冒烟。"""
    import cv2

    path = _video_devices()[0]
    idx = int(path.replace("/dev/video", "") or "0")
    cap = cv2.VideoCapture(idx)
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            pytest.skip(f"{path} 打不开或无帧")
        md = MotionDetector()
        cfg = MotionConfig(threshold=25, contour_area=50, lightning_threshold=0.95)
        md.process(frame, cfg)
        # 第二帧：允许有/无运动，只要不抛错
        r = md.process(frame, cfg)
        assert r.skipped in ("", "lightning", "recalibrate")
    finally:
        cap.release()
