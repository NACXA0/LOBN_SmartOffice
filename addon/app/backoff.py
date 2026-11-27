from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class ExpBackoff:
    """指数退避：失败拉长间隔，成功归零。"""

    base_sec: float = 1.0
    max_sec: float = 30.0
    factor: float = 2.0
    _failures: int = 0
    _next_ok_at: float = 0.0
    healthy: bool = True

    def ready(self) -> bool:
        return time.monotonic() >= self._next_ok_at

    def success(self) -> None:
        self._failures = 0
        self._next_ok_at = 0.0
        self.healthy = True

    def fail(self) -> float:
        self._failures += 1
        delay = min(self.max_sec, self.base_sec * (self.factor ** (self._failures - 1)))
        self._next_ok_at = time.monotonic() + delay
        self.healthy = False
        return delay
