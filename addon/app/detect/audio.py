from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class AudioConfig:
    enabled: bool = False
    min_rms: float = 0.02
    cooldown_sec: float = 30.0


@dataclass
class AudioEvent:
    triggered: bool
    rms: float = 0.0
    reason: str = ""


class AudioDetector:
    """音频能量检测（RMS）。输入为 float32 mono [-1,1]；无任意编解码，依赖上游供帧。"""

    def __init__(self) -> None:
        self._last_fire = 0.0

    def process(self, samples: list[float] | None, cfg: AudioConfig) -> AudioEvent:
        if not cfg.enabled:
            return AudioEvent(False, reason="disabled")
        if not samples:
            return AudioEvent(False, reason="empty")
        n = len(samples)
        acc = 0.0
        for x in samples:
            v = float(x)
            acc += v * v
        rms = (acc / max(1, n)) ** 0.5
        now = time.monotonic()
        if rms < cfg.min_rms:
            return AudioEvent(False, rms=rms)
        if now - self._last_fire < cfg.cooldown_sec:
            return AudioEvent(False, rms=rms, reason="cooldown")
        self._last_fire = now
        return AudioEvent(True, rms=rms)
