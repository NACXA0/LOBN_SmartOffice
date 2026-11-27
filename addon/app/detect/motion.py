from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import cv2

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    _HAS_CV2 = False


@dataclass
class MotionConfig:
    enabled: bool = True
    threshold: int = 30  # 1-255，越高越不敏感
    contour_area: int = 10
    improve_contrast: bool = False
    lightning_threshold: float = 0.8  # 0.3-1.0；帧变化比例超此则当闪电跳过
    frame_skip_threshold: float = 0.0  # 0=关闭；单帧变化比例过大则重校准
    delta_alpha: float = 0.2  # 帧差混合
    bg_alpha: float = 0.05  # 背景更新速度


@dataclass
class MotionResult:
    moving: bool
    area: int = 0
    ratio: float = 0.0
    skipped: str = ""  # lightning | recalibrate | disabled | ""
    boxes: list[tuple[float, float, float, float]] = field(default_factory=list)


def default_motion_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "threshold": 30,
        "contour_area": 10,
        "improve_contrast": False,
        "lightning_threshold": 0.8,
        "frame_skip_threshold": 0.0,
        "delta_alpha": 0.2,
        "bg_alpha": 0.05,
    }


def parse_motion_config(raw: dict | None) -> MotionConfig:
    d = default_motion_config()
    if raw:
        d.update({k: raw[k] for k in d if k in raw})
    return MotionConfig(
        enabled=bool(d["enabled"]),
        threshold=int(max(1, min(255, d["threshold"]))),
        contour_area=int(max(1, d["contour_area"])),
        improve_contrast=bool(d["improve_contrast"]),
        lightning_threshold=float(max(0.3, min(1.0, d["lightning_threshold"]))),
        frame_skip_threshold=float(max(0.0, min(1.0, d["frame_skip_threshold"] or 0))),
        delta_alpha=float(max(0.01, min(1.0, d["delta_alpha"]))),
        bg_alpha=float(max(0.001, min(1.0, d["bg_alpha"]))),
    )


def _poly_mask(h: int, w: int, polygons: list[list]) -> np.ndarray:
    """polygons 为归一化坐标；遮罩内像素=0（忽略），外=255。"""
    mask = np.full((h, w), 255, dtype=np.uint8)
    if not polygons:
        return mask
    if _HAS_CV2:
        for poly in polygons:
            if not poly or len(poly) < 3:
                continue
            pts = np.array(
                [[int(float(x) * (w - 1)), int(float(y) * (h - 1))] for x, y in poly],
                dtype=np.int32,
            )
            cv2.fillPoly(mask, [pts], 0)
        return mask
    # 无 cv2：矩形包围盒近似（测试兜底）
    for poly in polygons:
        if not poly or len(poly) < 3:
            continue
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        x0, x1 = int(min(xs) * (w - 1)), int(max(xs) * (w - 1))
        y0, y1 = int(min(ys) * (h - 1)), int(max(ys) * (h - 1))
        mask[y0 : y1 + 1, x0 : x1 + 1] = 0
    return mask


def _to_gray(frame_bgr: np.ndarray, improve_contrast: bool) -> np.ndarray:
    if frame_bgr.ndim == 2:
        gray = frame_bgr.astype(np.uint8)
    elif _HAS_CV2:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    else:
        # BT.601
        f = frame_bgr.astype(np.float32)
        gray = (0.114 * f[:, :, 0] + 0.587 * f[:, :, 1] + 0.299 * f[:, :, 2]).astype(np.uint8)
    if improve_contrast and _HAS_CV2:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    elif improve_contrast:
        # 简易直方图拉伸
        lo, hi = np.percentile(gray, [2, 98])
        if hi > lo:
            gray = np.clip((gray.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    return gray


class MotionDetector:
    """基于帧差的画面变动检测（对齐 Frigate 参数语义；实现依赖 OpenCV 优先）。"""

    def __init__(self) -> None:
        self._bg: np.ndarray | None = None
        self._prev: np.ndarray | None = None

    def reset(self) -> None:
        self._bg = None
        self._prev = None

    def process(
        self,
        frame_bgr: np.ndarray,
        cfg: MotionConfig,
        *,
        motion_masks: list[list] | None = None,
    ) -> MotionResult:
        if not cfg.enabled:
            return MotionResult(moving=False, skipped="disabled")
        if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
            return MotionResult(moving=False)

        gray = _to_gray(frame_bgr, cfg.improve_contrast)
        if _HAS_CV2:
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
        h, w = gray.shape[:2]
        ignore = _poly_mask(h, w, motion_masks or [])

        if self._bg is None:
            self._bg = gray.astype(np.float32)
            self._prev = gray.copy()
            return MotionResult(moving=False)

        # 帧差（混合）
        prev = self._prev if self._prev is not None else gray
        delta = np.abs(gray.astype(np.float32) - prev.astype(np.float32))
        if self._bg is not None:
            bg_delta = np.abs(gray.astype(np.float32) - self._bg)
            delta = cfg.delta_alpha * delta + (1.0 - cfg.delta_alpha) * bg_delta

        # 背景慢更新
        self._bg = (1.0 - cfg.bg_alpha) * self._bg + cfg.bg_alpha * gray.astype(np.float32)
        self._prev = gray.copy()

        changed = (delta >= float(cfg.threshold)).astype(np.uint8) * 255
        changed = np.where(ignore > 0, changed, 0).astype(np.uint8)
        changed_ratio = float(np.count_nonzero(changed)) / float(h * w)

        if cfg.frame_skip_threshold > 0 and changed_ratio >= cfg.frame_skip_threshold:
            self._bg = gray.astype(np.float32)
            return MotionResult(moving=False, ratio=changed_ratio, skipped="recalibrate")

        if changed_ratio >= cfg.lightning_threshold:
            return MotionResult(moving=False, ratio=changed_ratio, skipped="lightning")

        boxes: list[tuple[float, float, float, float]] = []
        area = 0
        if _HAS_CV2:
            contours, _ = cv2.findContours(changed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                a = int(cv2.contourArea(c))
                if a < cfg.contour_area:
                    continue
                area += a
                x, y, bw, bh = cv2.boundingRect(c)
                boxes.append((x / w, y / h, (x + bw) / w, (y + bh) / h))
        else:
            area = int(np.count_nonzero(changed))
            if area >= cfg.contour_area:
                ys, xs = np.where(changed > 0)
                boxes.append(
                    (
                        float(xs.min()) / w,
                        float(ys.min()) / h,
                        float(xs.max()) / w,
                        float(ys.max()) / h,
                    )
                )

        return MotionResult(
            moving=area >= cfg.contour_area and len(boxes) > 0,
            area=area,
            ratio=changed_ratio,
            boxes=boxes,
        )
