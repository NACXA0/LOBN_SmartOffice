from __future__ import annotations

import numpy as np
import pytest

from app.store import GalleryStore


@pytest.fixture
def store(tmp_path):
    return GalleryStore(tmp_path / "people.sqlite3")


def test_booking_enroll_is_credential_not_visit(store: GalleryStore):
    vec = np.random.randn(8).astype(np.float32)
    store.commit_enrollment(
        "u100",
        "学员甲",
        "mock-v1",
        [vec],
        [None],
        person_kind="student",
        origin="booking",
        mark_sighted=False,
    )
    p = store.get_person("u100")
    assert p is not None
    assert p.origin == "booking"
    assert p.person_kind == "student"
    assert p.sighted is False
    assert p.visit_count == 0
    assert store.can_open_by_face("u100") is True  # 有凭证可开门，但未造访
    cred = store.list_persons(scope="credential")
    assert any(x.user_id == "u100" for x in cred)
    assert not any(x.user_id == "u100" for x in store.list_persons(scope="sighted"))


def test_visit_marks_sighted(store: GalleryStore):
    store.upsert_person("u100", "学员甲", "accepted", person_kind="student", origin="booking")
    vid = store.record_visit("u100", camera="door", space_id="front_gate", kind="match", similarity=0.55)
    assert vid is not None
    p = store.get_person("u100")
    assert p.sighted is True
    assert p.visit_count == 1
    assert p.last_seen_at is not None
    # 去抖
    assert store.record_visit("u100", camera="door", min_interval_sec=600) is None
    assert store.get_person("u100").visit_count == 1
    assert len(store.list_visits("u100")) == 1


def test_ingest_sighting_and_link(store: GalleryStore):
    vec = np.random.randn(8).astype(np.float32)
    stranger = store.ingest_sighting(vec, model_version="mock-v1", camera="cam1", similarity=0.1)
    assert stranger.person_kind == "stranger"
    assert stranger.sighted is True
    assert stranger.visit_count == 1
    assert store.can_open_by_face(stranger.user_id) is False

    store.upsert_person("staff1", "店员", "accepted", person_kind="staff", origin="office")
    store.commit_enrollment("staff1", "店员", "mock-v1", [np.random.randn(8).astype(np.float32)], [None])
    merged = store.link_persons(stranger.user_id, "staff1")
    assert merged.user_id == "staff1"
    assert store.get_person(stranger.user_id) is None
    assert merged.sighted is True
    assert merged.visit_count >= 1
    assert any(v["user_id"] == "staff1" for v in store.list_visits("staff1"))


def test_scope_stranger(store: GalleryStore):
    store.ingest_sighting(np.ones(4, dtype=np.float32), model_version="m")
    store.upsert_person("s1", "员工", "accepted", person_kind="staff")
    strangers = store.list_persons(scope="stranger")
    assert len(strangers) == 1
    assert strangers[0].person_kind == "stranger"
