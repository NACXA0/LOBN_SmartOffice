from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from .ratelimit import TokenBucket

_LOGGER = logging.getLogger(__name__)


class AiClient:
    """固定 ai_base_url；只收本地记录引用/单帧/短音频，无任意 URL。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        per_minute: float = 6.0,
        per_day: float = 200.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "gpt-4o-mini"
        self.bucket = TokenBucket(per_minute=per_minute, per_day=per_day)

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def explain_image(
        self,
        http: httpx.AsyncClient,
        image_path: Path,
        prompt: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "reason": "ai_not_configured"}
        if not self.bucket.allow(session_id=session_id):
            return {"ok": False, "reason": "rate_limited", "status": 429}
        if not image_path.is_file():
            return {"ok": False, "reason": "no_frame"}
        raw = image_path.read_bytes()
        if len(raw) > 2_000_000:
            return {"ok": False, "reason": "frame_too_large"}
        b64 = base64.b64encode(raw).decode("ascii")
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "max_tokens": 400,
        }
        try:
            r = await http.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
                timeout=10.0,
            )
        except Exception as e:
            _LOGGER.warning("ai explain failed: %s", e)
            return {"ok": False, "reason": "ai_error"}
        if r.status_code >= 400:
            return {"ok": False, "reason": f"ai_http_{r.status_code}"}
        data = r.json()
        text = ""
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception:
            text = str(data)[:500]
        return {"ok": True, "text": text}

    async def transcribe(
        self,
        http: httpx.AsyncClient,
        audio: bytes,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "reason": "ai_not_configured"}
        if not self.bucket.allow(session_id=session_id):
            return {"ok": False, "reason": "rate_limited", "status": 429}
        if len(audio) > 1_500_000:
            return {"ok": False, "reason": "audio_too_large"}
        # OpenAI-compatible multipart; 无自动重试
        try:
            r = await http.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                data={"model": "whisper-1"},
                files={"file": ("note.webm", audio, "audio/webm")},
                timeout=10.0,
            )
        except Exception as e:
            _LOGGER.warning("transcribe failed: %s", e)
            return {"ok": False, "reason": "ai_error"}
        if r.status_code >= 400:
            return {"ok": False, "reason": f"ai_http_{r.status_code}"}
        data = r.json()
        return {"ok": True, "text": str(data.get("text") or "")}

    async def assist(
        self,
        http: httpx.AsyncClient,
        question: str,
        context: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {"ok": True, "text": context, "mode": "local"}
        if not self.bucket.allow(session_id=session_id, session_limit=30):
            return {"ok": False, "reason": "rate_limited", "status": 429}
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是办公室总管助手。只根据给定材料回答，不要编造开门或改布防。建议动作用简短列表。",
                },
                {"role": "user", "content": f"材料：\n{context}\n\n问题：{question}"},
            ],
            "max_tokens": 500,
        }
        try:
            r = await http.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
                timeout=10.0,
            )
        except Exception:
            return {"ok": True, "text": context, "mode": "local_fallback"}
        if r.status_code >= 400:
            return {"ok": True, "text": context, "mode": "local_fallback"}
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception:
            text = context
        return {"ok": True, "text": text, "mode": "online"}
