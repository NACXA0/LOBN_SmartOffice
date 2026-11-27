from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

try:
    import cv2

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    _HAS_CV2 = False


@dataclass
class Detection:
    label: str  # person | leftover | coco…
    score: float
    box: tuple[float, float, float, float]  # x1,y1,x2,y2 normalized 0-1
    in_polygon: bool = True


class PersonDetector(Protocol):
    """可替换检测接口；重模型可放同 Add-on 伴随进程。"""

    ready: bool

    def detect(self, frame_bgr: np.ndarray, polygon: list | None = None) -> list[Detection]: ...


def _point_in_poly(x: float, y: float, poly: list) -> bool:
    if not poly or len(poly) < 3:
        return True
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


class MockDetector:
    """开发态：帧非空则视为中心有一个人；不声称真实检测。"""

    ready = True

    def detect(self, frame_bgr: np.ndarray, polygon: list | None = None) -> list[Detection]:
        if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
            return []
        cx, cy = 0.5, 0.5
        in_poly = _point_in_poly(cx, cy, polygon or [])
        if not in_poly:
            return []
        return [Detection(label="person", score=0.9, box=(0.35, 0.2, 0.65, 0.9), in_polygon=True)]


class HogPersonDetector:
    """OpenCV HOG 默认行人检测器（成熟算法，非自研）。无 GPU；适合门禁旁路人数估计。"""

    ready = True

    def __init__(self) -> None:
        if not _HAS_CV2:
            raise RuntimeError("opencv_required")
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame_bgr: np.ndarray, polygon: list | None = None) -> list[Detection]:
        if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
            return []
        h, w = frame_bgr.shape[:2]
        if h < 64 or w < 32:
            return []
        # HOG 对偏小分辨率更稳：先缩放到约 480 宽
        scale = 1.0
        work = frame_bgr
        if w > 640:
            scale = 640.0 / w
            work = cv2.resize(frame_bgr, (int(w * scale), int(h * scale)))
        rects, weights = self._hog.detectMultiScale(
            work,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        out: list[Detection] = []
        wh, ww = work.shape[:2]
        for (x, y, bw, bh), wt in zip(rects, weights):
            x1 = float(x) / ww
            y1 = float(y) / wh
            x2 = float(x + bw) / ww
            y2 = float(y + bh) / wh
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            in_poly = _point_in_poly(cx, cy, polygon or [])
            if not in_poly:
                continue
            score = float(wt[0]) if hasattr(wt, "__len__") else float(wt)
            # HOG 权重常 >1；压到 0–1 便于与 Frigate 风格 min_score 对齐
            score_n = max(0.0, min(1.0, score / 2.0))
            out.append(Detection(label="person", score=score_n, box=(x1, y1, x2, y2), in_polygon=True))
        return out


def build_detector(kind: str = "mock") -> PersonDetector:
    k = (kind or "mock").lower().strip()
    if k in ("hog", "opencv"):
        if _HAS_CV2:
            return HogPersonDetector()
        return MockDetector()
    # onnx / companion 以后在此分支
    return MockDetector()


def count_persons(dets: list[Detection]) -> int:
    return sum(1 for d in dets if d.label == "person" and d.in_polygon)


def has_leftover(dets: list[Detection]) -> bool:
    return any(d.label == "leftover" and d.in_polygon for d in dets)
