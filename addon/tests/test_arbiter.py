from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.access import AccessArbiter, AccessRequest
from app.mqtt_bus import MqttBus
from app.store import GalleryStore


@pytest.fixture()
def store(tmp_path: Path) -> GalleryStore:
    return GalleryStore(tmp_path / "a.sqlite3")


@pytest.mark.asyncio
async def test_arbiter_grant_and_door_cooldown(store: GalleryStore):
    bus = MqttBus("off", 1883, "", "")
    arb = AccessArbiter(store, bus, door_cooldown_sec=30.0)
    req = AccessRequest(source="face_match", user_id="1", display_name="甲", door="front_gate")
    r1 = await arb.apply(req)
    assert r1.result == "grant" and r1.command_id and r1.grant
    assert r1.grant["reason"] == "face_match"
    rows = store.list_access_ledger(limit=5)
    assert rows and rows[0]["result"] == "grant"

    r2 = await arb.apply(req)
    assert r2.result == "drop" and r2.reason == "door_cooldown"
    assert store.door_cooldown_active("front_gate", time.monotonic())


@pytest.mark.asyncio
async def test_arbiter_schedule_source(store: GalleryStore):
    bus = MqttBus("off", 1883, "", "")
    arb = AccessArbiter(store, bus, door_cooldown_sec=0)
    req = AccessRequest(source="schedule", user_id="9", display_name="乙", door="classroom_1")
    r = await arb.apply(req)
    assert r.result == "grant"
    assert r.grant and r.grant["reason"] == "schedule"
