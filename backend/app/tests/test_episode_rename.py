"""PATCH /episodes/{id}: renaming and moving an episode (no database needed)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.db import get_session
from app.google_repo import sync as google_sync
from app.main import app
from app.models import Episode, Project

PROJECT_ID = uuid.uuid4()
OTHER_PROJECT_ID = uuid.uuid4()


class FakeSession:
    def __init__(self, episode: Episode) -> None:
        self.episode = episode
        self.projects = {PROJECT_ID: Project(id=PROJECT_ID, slug="dan-ba-30",
                                             name="Đàn bà 30+"),
                         OTHER_PROJECT_ID: Project(id=OTHER_PROJECT_ID, slug="khac",
                                                   name="Khác")}
        self.commits = 0

    def get(self, model, key):
        if model is Project:
            return self.projects.get(key)
        return self.episode if key == self.episode.id else None

    def commit(self):
        self.commits += 1


@pytest.fixture
def world(monkeypatch):
    now = datetime.now(UTC)
    ep = Episode(id=uuid.uuid4(), slug="ban-ghi-moi-3", title="Bản ghi mới 3",
                 project_id=PROJECT_ID, status="transcribed", created_at=now, updated_at=now)
    fake = FakeSession(ep)
    synced: list = []
    project_synced: list = []
    monkeypatch.setattr(google_sync, "enqueue", lambda s, eid, **kw: synced.append(eid))
    monkeypatch.setattr(google_sync, "enqueue_project",
                        lambda s, pid: project_synced.append(pid))
    app.dependency_overrides[get_session] = lambda: fake
    app.dependency_overrides[deps.require_editor] = lambda: "nam"
    yield TestClient(app), fake, synced, project_synced
    app.dependency_overrides.clear()


def test_rename_sets_title_keeps_slug_and_queues_sync(world):
    client, fake, synced, project_synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}",
                     json={"title": "  Bài giảng triết học "})
    assert r.status_code == 200
    assert r.json()["title"] == "Bài giảng triết học"
    assert r.json()["slug"] == "ban-ghi-moi-3"
    assert synced == [fake.episode.id]
    assert project_synced == []
    assert fake.commits == 1


def test_same_title_queues_nothing(world):
    client, fake, synced, project_synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}", json={"title": "Bản ghi mới 3"})
    assert r.status_code == 200
    assert synced == []
    assert project_synced == []


def test_blank_title_rejected(world):
    client, fake, synced, project_synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}", json={"title": "   "})
    assert r.status_code == 400
    assert fake.episode.title == "Bản ghi mới 3"
    assert synced == []


def test_unknown_episode_404(world):
    client, _, _, _ = world
    assert client.patch(f"/api/episodes/{uuid.uuid4()}", json={"title": "x"}).status_code == 404


def test_move_to_another_project_queues_both_syncs(world):
    client, fake, synced, project_synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}",
                     json={"project_id": str(OTHER_PROJECT_ID)})
    assert r.status_code == 200
    assert r.json()["project_id"] == str(OTHER_PROJECT_ID)
    assert fake.episode.project_id == OTHER_PROJECT_ID
    assert synced == [fake.episode.id]          # the new project's Doc/Sheet
    assert project_synced == [PROJECT_ID]        # the old project's Sheet loses the row


def test_move_to_unknown_project_404(world):
    client, fake, synced, project_synced = world
    r = client.patch(f"/api/episodes/{fake.episode.id}",
                     json={"project_id": str(uuid.uuid4())})
    assert r.status_code == 404
    assert synced == [] and project_synced == []
