from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.store import GalleryStore


@pytest.fixture
def store(tmp_path):
    return GalleryStore(tmp_path / "manual.sqlite3")


def test_create_person_manual_without_face(store: GalleryStore):
    p = store.create_person(display_name="张三", person_kind="visitor", phone="13800000000", notes="客户参观")
    assert p.user_id.startswith("manual_")
    assert p.origin == "manual"
    assert p.face_status == "none"
    assert p.sighted is False
    assert p.visit_count == 0
    assert p.phone == "13800000000"
    assert store.can_open_by_face(p.user_id) is False


def test_create_person_custom_id_and_photos(store: GalleryStore, tmp_path):
    p = store.create_person(user_id="vip_1", display_name="李四", person_kind="staff")
    assert p.user_id == "vip_1"
    with pytest.raises(ValueError):
        store.create_person(user_id="vip_1", display_name="重复")

    vec = np.random.randn(16).astype(np.float32)
    img_path = tmp_path / "face.jpg"
    Image.new("RGB", (120, 120), (40, 80, 120)).save(img_path, format="JPEG")
    stats = store.append_person_photos("vip_1", "mock-v1", [vec], [str(img_path)], max_photos=3)
    assert stats["added"] == 1
    assert stats["total"] == 1
    p2 = store.get_person("vip_1")
    assert p2.face_status == "accepted"
    assert store.can_open_by_face("vip_1") is True
    photos = store.list_person_photos("vip_1")
    assert len(photos) == 1
    emb_id = photos[0]["id"]
    assert store.delete_person_photo("vip_1", emb_id) is True
    assert store.get_person("vip_1").face_status == "none"


def test_photo_cap_prunes_oldest(store: GalleryStore, tmp_path):
    store.create_person(user_id="cap1", display_name="限幅")
    for i in range(5):
        path = tmp_path / f"f{i}.jpg"
        Image.new("RGB", (64, 64), (i * 20, 10, 10)).save(path)
        store.append_person_photos(
            "cap1",
            "mock-v1",
            [np.random.randn(8).astype(np.float32)],
            [str(path)],
            max_photos=3,
        )
    assert len(store.list_person_photos("cap1")) == 3


def test_ignore_blocks_door(store: GalleryStore):
    store.create_person(user_id="ig1", display_name="忽略")
    store.append_person_photos(
        "ig1",
        "m",
        [np.ones(8, dtype=np.float32)],
        [None],
    )
    assert store.can_open_by_face("ig1") is True
    store.update_person("ig1", ignored=True)
    assert store.can_open_by_face("ig1") is False


def test_update_person_fields(store: GalleryStore):
    p = store.create_person(display_name="王五", person_kind="staff")
    u = store.update_person(p.user_id, person_kind="visitor", notes="临时", phone="100")
    assert u.person_kind == "visitor"
    assert u.notes == "临时"
    assert u.phone == "100"
