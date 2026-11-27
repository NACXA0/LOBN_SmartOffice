from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """简单令牌桶：每分钟 + 每日双限。超限返回 False。"""

    per_minute: float = 6.0
    per_day: float = 200.0
    _minute_tokens: float = field(default=0.0, init=False)
    _day_tokens: float = field(default=0.0, init=False)
    _minute_ts: float = field(default=0.0, init=False)
    _day_ts: float = field(default=0.0, init=False)
    _session_counts: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        now = time.monotonic()
        self._minute_tokens = self.per_minute
        self._day_tokens = self.per_day
        self._minute_ts = now
        self._day_ts = now

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed_m = now - self._minute_ts
        if elapsed_m > 0:
            self._minute_tokens = min(self.per_minute, self._minute_tokens + elapsed_m * (self.per_minute / 60.0))
            self._minute_ts = now
        elapsed_d = now - self._day_ts
        if elapsed_d > 0:
            self._day_tokens = min(self.per_day, self._day_tokens + elapsed_d * (self.per_day / 86400.0))
            self._day_ts = now

    def allow(self, *, session_id: str | None = None, session_limit: int = 30) -> bool:
        self._refill()
        if session_id:
            used = self._session_counts.get(session_id, 0)
            if used >= session_limit:
                return False
        if self._minute_tokens < 1.0 or self._day_tokens < 1.0:
            return False
        self._minute_tokens -= 1.0
        self._day_tokens -= 1.0
        if session_id:
            self._session_counts[session_id] = self._session_counts.get(session_id, 0) + 1
        return True
