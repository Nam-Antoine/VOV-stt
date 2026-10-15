"""PATCH /hotwords/{id}: renaming a term must not 500 on a collision (no database
needed — see test_episode_rename.py for the pattern).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.db import get_session
from app.main import app
from app.models import Hotword


class FakeSession:
    def __init__(self, hotwords: list[Hotword]) -> None:
        self.hotwords = {h.id: h for h in hotwords}
        self.commits = 0

    def get(self, model, key):
        return self.hotwords.get(key) if model is Hotword else None

    def scalar(self, query):
        # Only "does another hotword already have this term" goes through here.
        wanted = next(iter(query.compile().params.values()))
        return next((h for h in self.hotwords.values() if h.term == wanted), None)

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def world(monkeypatch):
    now = datetime.now(UTC)
    existing = Hotword(id=1, term="ĐÀN BÀ BA MƯƠI CỘNG", weight=1.5, active=True,
                       created_at=now)
    other = Hotword(id=2, term="VOV2", weight=1.0, active=True, created_at=now)
    fake = FakeSession([existing, other])
    app.dependency_overrides[get_session] = lambda: fake
    app.dependency_overrides[deps.require_admin] = lambda: "nam"
    yield TestClient(app), fake
    app.dependency_overrides.clear()


def test_renaming_to_an_existing_term_is_409_not_500(world):
    client, fake = world
    r = client.patch("/api/hotwords/2", json={"term": "ĐÀN BÀ BA MƯƠI CỘNG"})
    assert r.status_code == 409
    assert fake.hotwords[2].term == "VOV2"  # unchanged
    assert fake.commits == 0


def test_renaming_to_its_own_current_term_is_a_no_op_not_a_conflict(world):
    client, fake = world
    r = client.patch("/api/hotwords/1", json={"term": "ĐÀN BÀ BA MƯƠI CỘNG", "weight": 2.0})
    assert r.status_code == 200
    assert fake.hotwords[1].weight == 2.0


def test_renaming_to_a_free_term_succeeds(world):
    client, fake = world
    r = client.patch("/api/hotwords/2", json={"term": "ĐÀN BÀ"})
    assert r.status_code == 200
    assert fake.hotwords[2].term == "ĐÀN BÀ"
