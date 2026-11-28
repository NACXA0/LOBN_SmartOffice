from __future__ import annotations

import pytest

from app.store import GalleryStore


@pytest.fixture
def store(tmp_path):
    return GalleryStore(tmp_path / "scene.sqlite3")


def test_access_mode_always_open(store: GalleryStore):
    store.upsert_space("inner_door", name="里门", kind="door", camera="cam_inner")
    s = store.set_space_access_mode("inner_door", "always_open")
    assert s["access_mode"] == "always_open"
    bad = store.set_space_access_mode("inner_door", "nope")
    assert bad["access_mode"] == "face"
    hit = store.find_space_by_camera("cam_inner")
    assert hit is not None
    assert hit["id"] == "inner_door"
    assert hit["access_mode"] == "face"  # 上次 invalid 重置为 face；再设回
    store.set_space_access_mode("inner_door", "always_open")
    assert store.find_space_by_camera("cam_inner")["access_mode"] == "always_open"


def test_scene_binds_spaces_and_filters(store: GalleryStore):
    store.upsert_space("gate", name="大门", kind="door")
    store.upsert_space("room_a", name="教室A", kind="room")
    store.upsert_space("room_b", name="教室B", kind="room")
    sc = store.upsert_scene(
        "classroom_a",
        name="教室A场景",
        kind="classroom",
        adapter="booking",
        space_ids=["room_a", "gate"],
    )
    assert sc["id"] == "classroom_a"
    assert "classroom_a" in (store.get_space("room_a") or {}).get("scene_ids", [])
    spaces = store.list_spaces_for_scene("classroom_a")
    ids = {s["id"] for s in spaces}
    assert ids == {"room_a", "gate"}
    assert "room_b" not in ids


def test_visits_filtered_by_scene_spaces(store: GalleryStore):
    store.upsert_space("room_a", name="A", kind="room")
    store.upsert_person("u1", "甲", "accepted")
    store.record_visit("u1", camera="c1", space_id="room_a", kind="sight", min_interval_sec=0)
    store.record_visit("u1", camera="c2", space_id="other", kind="sight", min_interval_sec=0)
    rows = store.list_visits_for_spaces(["room_a"], limit=10)
    assert len(rows) == 1
    assert rows[0]["space_id"] == "room_a"
