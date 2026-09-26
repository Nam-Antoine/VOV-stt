"""PATCH /episodes/{id}: renaming an episode (no database needed)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.db import get_session
from app.google_repo import sync as google_sync
from app.main import app
from app.models import Episode


class FakeSession:
    def __init__(self, episode: Episode) -> None:
        self.episode = episode
        self.commits = 0

    def get(self, model, key):
        return self.episode if key == self.episode.id else None

    def commit(self):
        self.commits += 1


@pytest.fixture
def world(monkeypatch):
    now = datetime.now(UTC)
    ep = Episode(id=uuid.uuid4(), slug="ban-ghi-moi-3", title="Bản ghi mới 3",
                 status="transcribed", created_at=now, updated_at=now)
    fake = FakeSession(ep)
    synced: list = []
    monkeypatch.setattr(google_sync, "enqueue", lambda s, eid, **kw: synced.append(eid))
    app.dependency_overrides[get_session] = lambda: fake
    app.dependency_overrides[deps.require_editor] = lambda: "nam"
    yield TestClient(app), fake, synced
    app.dependency_overrides.clear()


def test_rename_sets_title_keeps_slug_and_queues_sync(world):
    client, fake, synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}",
                     json={"title": "  Bài giảng triết học "})
    assert r.status_code == 200
    assert r.json()["title"] == "Bài giảng triết học"
    assert r.json()["slug"] == "ban-ghi-moi-3"
    assert synced == [fake.episode.id]
    assert fake.commits == 1


def test_same_title_queues_nothing(world):
    client, fake, synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}", json={"title": "Bản ghi mới 3"})
    assert r.status_code == 200
    assert synced == []


def test_blank_title_rejected(world):
    client, fake, synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}", json={"title": "   "})
    assert r.status_code == 400
    assert fake.episode.title == "Bản ghi mới 3"
    assert synced == []


def test_unknown_episode_404(world):
    client, _, _ = world
    assert client.patch(f"/api/episodes/{uuid.uuid4()}", json={"title": "x"}).status_code == 404
