from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.access import AccessArbiter, AccessRequest
from app.alerts import Alert, AlertBus
from app.arming import schedule_armed_now
from app.assets_svc import AssetService
from app.ratelimit import TokenBucket
from app.store import GalleryStore


class FakeBus:
    def __init__(self) -> None:
        self.grants: list[dict] = []
        self.retained: list[tuple[str, dict]] = []
        self.enabled = True

    async def publish_grant(self, grant: dict) -> bool:
        self.grants.append(grant)
        return True

    async def publish_retained(self, topic: str, payload: dict) -> bool:
        self.retained.append((topic, payload))
        return True

    async def publish(self, topic: str, payload: dict, *, retain: bool = False) -> bool:
        if retain:
            return await self.publish_retained(topic, payload)
        return True


@pytest.fixture
def store(tmp_path: Path) -> GalleryStore:
    return GalleryStore(tmp_path / "t.sqlite3")


def test_space_seed_and_polygon(store: GalleryStore) -> None:
    store.ensure_default_spaces("front_gate", ["front_desk"])
    s = store.get_space("front_gate")
    assert s and s["kind"] == "door"
    store.set_space_polygon("front_gate", [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]])
    assert len(store.get_space("front_gate")["polygon"]) == 3


def test_staff_manual_grant(store: GalleryStore) -> None:
    bus = FakeBus()
    arb = AccessArbiter(store, bus, door_cooldown_sec=1.0)

    async def _run() -> None:
        r = await arb.apply(
            AccessRequest(source="staff_manual", user_id="staff", display_name="店员", door="front_gate")
        )
        assert r.result == "grant"
        assert len(bus.grants) == 1
        r2 = await arb.apply(
            AccessRequest(source="staff_manual", user_id="staff2", display_name="店员2", door="front_gate")
        )
        assert r2.result == "drop"
        assert r2.reason == "door_cooldown"

    asyncio.run(_run())


def test_schedule_source(store: GalleryStore) -> None:
    bus = FakeBus()
    arb = AccessArbiter(store, bus, door_cooldown_sec=0.0)

    async def _run() -> None:
        store.upsert_policy_window(
            "g1",
            space_id="classroom_1",
            subject_id="1001",
            subject_name="学员",
            source="booking",
            window_start=time.time() - 10,
            window_end=time.time() + 600,
        )
        r = await arb.apply(
            AccessRequest(source="schedule", user_id="1001", door="classroom_1", detail={"policy_id": "g1"})
        )
        assert r.result == "grant"
        assert bus.grants[0]["reason"] == "schedule"

    asyncio.run(_run())


def test_visitor_expiry(store: GalleryStore) -> None:
    store.upsert_person("v1", "访客", "accepted", enabled=True)
    store.set_person_visitor("v1", person_kind="visitor", valid_until=time.time() - 10)
    n = store.expire_visitors()
    assert n == 1
    p = store.get_person("v1")
    assert p and not p.enabled


def test_allowlist_empty_needs_force(store: GalleryStore) -> None:
    bus = FakeBus()
    svc = AssetService(store, bus)

    async def _run() -> None:
        r = await svc.publish_allowlist("classroom_1", force_empty=False)
        assert r["ok"] is False
        assert r["reason"] == "empty_needs_force"
        r2 = await svc.publish_allowlist("classroom_1", force_empty=True)
        assert r2["ok"] is True
        assert r2["rev"] == 1
        store.upsert_asset("TAG1", name="相机", space_id="classroom_1")
        r3 = await svc.publish_allowlist("classroom_1")
        assert r3["ok"] is True
        assert "TAG1" in r3["tags"]
        assert r3["rev"] == 2

    asyncio.run(_run())


def test_alert_debounce_and_latch(store: GalleryStore) -> None:
    bus = AlertBus(store, debounce_sec=60.0)

    async def _run() -> None:
        a1 = await bus.emit(Alert(kind="dwell", space_id="r1", title="滞留", latch_key="r1:dwell:x"))
        a2 = await bus.emit(Alert(kind="dwell", space_id="r1", title="滞留", latch_key="r1:dwell:x"))
        assert a1 is not None
        assert a2 is None
        b1 = await bus.emit(Alert(kind="stranger", space_id="r1", title="陌生人"))
        b2 = await bus.emit(Alert(kind="stranger", space_id="r1", title="陌生人"))
        assert b1 is not None
        assert b2 is None

    asyncio.run(_run())


def test_rate_limit_429() -> None:
    b = TokenBucket(per_minute=2, per_day=10)
    assert b.allow()
    assert b.allow()
    assert not b.allow()


def test_rfid_event_dedupe(store: GalleryStore) -> None:
    assert store.mark_rfid_seen("e1") is True
    assert store.mark_rfid_seen("e1") is False


def test_arming_schedule() -> None:
    from datetime import datetime

    # Monday 10:00
    now = datetime(2026, 3, 2, 10, 0)  # Monday
    assert schedule_armed_now([{"dow": 0, "start": "09:00", "end": "12:00"}], now)
    assert not schedule_armed_now([{"dow": 0, "start": "13:00", "end": "18:00"}], now)


def test_dashboard_cache(store: GalleryStore) -> None:
    store.ensure_default_spaces("front_gate", ["cam"])
    d1 = store.dashboard()
    d2 = store.dashboard()
    assert d1["office"]["open_alerts"] == d2["office"]["open_alerts"]
    store.insert_alert(space_id="front_gate", kind="ops", severity="info", title="x")
    d3 = store.dashboard()
    assert d3["office"]["open_alerts"] >= 1


def test_person_space_restriction(store: GalleryStore) -> None:
    store.upsert_person("v2", "访客", "accepted")
    store.set_person_visitor("v2", allowed_spaces="room_a", valid_until=time.time() + 3600)
    assert store.person_allowed_in_space("v2", "room_a")
    assert not store.person_allowed_in_space("v2", "room_b")
