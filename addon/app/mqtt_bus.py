from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

OnMessage = Callable[[str, dict[str, Any]], Awaitable[None]]


class MqttBus:
    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self.host = (host or "").strip()
        self.port = port
        self.user = user
        self.password = password
        self._client = None
        self._task: asyncio.Task | None = None
        self._fail_logged = False
        self._handler: OnMessage | None = None

    @property
    def enabled(self) -> bool:
        h = self.host.lower()
        return h not in ("", "off", "disabled", "none", "-")

    async def start(self, on_message: OnMessage) -> None:
        self._handler = on_message
        if not self.enabled:
            _LOGGER.info("MQTT disabled (host=%r); 采集/比对 API 仍可用", self.host)
            return
        try:
            from aiomqtt import Client
        except ImportError:
            _LOGGER.warning("aiomqtt missing; MQTT disabled")
            return

        async def _run() -> None:
            while True:
                try:
                    async with Client(
                        hostname=self.host,
                        port=self.port,
                        username=self.user or None,
                        password=self.password or None,
                    ) as client:
                        self._client = client
                        self._fail_logged = False
                        await client.subscribe("frigate/events")
                        await client.subscribe("home/+/door/state")
                        await client.subscribe("home/+/rfid/event")
                        _LOGGER.info("mqtt subscribed frigate/events + door/state + rfid/event @ %s", self.host)
                        async for message in client.messages:
                            try:
                                payload = json.loads(message.payload.decode("utf-8"))
                            except Exception:
                                # door/state 可能是纯文本 open/closed
                                raw = message.payload.decode("utf-8", errors="ignore").strip()
                                topic = str(message.topic)
                                if "/door/state" in topic:
                                    payload = {"state": raw}
                                else:
                                    continue
                            topic = str(message.topic)
                            if self._handler:
                                await self._handler(topic, payload if isinstance(payload, dict) else {"raw": payload})
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._client = None
                    if not self._fail_logged:
                        _LOGGER.warning(
                            "mqtt unavailable (%s: %s); will retry every 30s — "
                            "本机开发可设 MQTT_HOST=off",
                            type(e).__name__,
                            e,
                        )
                        self._fail_logged = True
                    await asyncio.sleep(30)

        self._task = asyncio.create_task(_run())

    async def publish(self, topic: str, payload: dict[str, Any], *, retain: bool = False) -> bool:
        if not self.enabled:
            _LOGGER.debug("mqtt off; skip publish %s", topic)
            return True
        if not self._client:
            _LOGGER.warning("mqtt not connected; drop %s", topic)
            return False
        await self._client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            retain=retain,
        )
        return True

    async def publish_retained(self, topic: str, payload: dict[str, Any]) -> bool:
        return await self.publish(topic, payload, retain=True)

    async def publish_grant(self, grant: dict[str, Any]) -> bool:
        """返回 True 表示已发出，或本机关闭 MQTT（开发态视为成功以便走审计）。"""
        if not self.enabled:
            _LOGGER.info("mqtt off; grant not published %s", grant.get("command_id"))
            return True
        return await self.publish("business/access/grant", grant)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
