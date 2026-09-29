"""Projects CRUD (no database needed — see test_episode_rename.py for the pattern).

``_counts`` (a grouped SQL query) is stubbed out here rather than faked at the SQL
level, same as the rest of this suite avoids a real engine; its shape is exercised live
against the real DB as part of deploying this feature.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api import projects as projects_api
from app.db import get_session
from app.google_repo import sync as google_sync
from app.main import app
from app.models import Project

EXISTING_ID = uuid.uuid4()


class FakeSession:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.projects: dict[uuid.UUID, Project] = {
            EXISTING_ID: Project(id=EXISTING_ID, slug="dan-ba-30", name="Đàn bà 30+",
                                 created_at=now),
        }
        self.episode_counts: dict[uuid.UUID, int] = {EXISTING_ID: 0}
        self.deleted: list[uuid.UUID] = []
        self.commits = 0

    def get(self, model, key):
        if model is Project:
            return self.projects.get(key)
        return None

    def add(self, obj) -> None:
        if isinstance(obj, Project):
            if obj.id is None:
                obj.id = uuid.uuid4()
            # A real commit gets this back from the server_default; simulate that.
            if obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            self.projects[obj.id] = obj
            self.episode_counts.setdefault(obj.id, 0)

    def delete(self, obj) -> None:
        self.deleted.append(obj.id)
        self.projects.pop(obj.id, None)

    def commit(self) -> None:
        self.commits += 1

    def scalar(self, query):
        """Two different ``session.scalar`` callers go through here:

        - ``_unique_slug``'s "does this slug exist" check (create_project) — always
          "no", the fake never has a colliding slug;
        - ``delete_project``'s episode-count check — ``self._pending_count``.
        """
        if "projects.slug" in str(query):
            return None
        return self._pending_count

    _pending_count = 0

    def scalars(self, _query):
        return list(self.projects.values())


@pytest.fixture
def world(monkeypatch):
    fake = FakeSession()
    synced: list = []
    monkeypatch.setattr(google_sync, "enqueue_project", lambda s, pid: synced.append(pid))
    monkeypatch.setattr(projects_api, "_counts", lambda s, ids: {
        pid: (fake.episode_counts.get(pid, 0), 0, 0, 0.0) for pid in ids
    })
    app.dependency_overrides[get_session] = lambda: fake
    app.dependency_overrides[deps.require_editor] = lambda: "nam"
    app.dependency_overrides[deps.require_admin] = lambda: "nam"
    yield TestClient(app), fake, synced
    app.dependency_overrides.clear()


def test_create_project_slugifies_the_name_and_queues_a_sync(world):
    client, fake, synced = world
    r = client.post("/api/projects", json={"name": "Chuyện đêm khuya", "description": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "chuyen-dem-khuya"
    assert body["name"] == "Chuyện đêm khuya"
    assert body["n_episodes"] == 0
    assert len(synced) == 1 and synced[0] in fake.projects


def test_create_blank_name_rejected(world):
    client, _, synced = world
    r = client.post("/api/projects", json={"name": "   "})
    assert r.status_code == 400
    assert synced == []


def test_list_projects_includes_counts(world):
    client, fake, _ = world
    fake.episode_counts[EXISTING_ID] = 12
    r = client.get("/api/projects")
    assert r.status_code == 200
    rows = {p["id"]: p for p in r.json()}
    assert rows[str(EXISTING_ID)]["n_episodes"] == 12


def test_rename_project_queues_a_sync_only_when_the_name_changes(world):
    client, fake, synced = world
    r = client.patch(f"/api/projects/{EXISTING_ID}", json={"description": "vẫn tên cũ"})
    assert r.status_code == 200
    assert synced == []

    r = client.patch(f"/api/projects/{EXISTING_ID}", json={"name": "Đàn bà 40+"})
    assert r.status_code == 200
    assert r.json()["name"] == "Đàn bà 40+"
    assert synced == [EXISTING_ID]


def test_rename_to_blank_rejected(world):
    client, fake, synced = world
    r = client.patch(f"/api/projects/{EXISTING_ID}", json={"name": "   "})
    assert r.status_code == 400
    assert fake.projects[EXISTING_ID].name == "Đàn bà 30+"
    assert synced == []


def test_delete_refuses_a_project_with_episodes(world):
    client, fake, _ = world
    fake._pending_count = 3
    r = client.delete(f"/api/projects/{EXISTING_ID}")
    assert r.status_code == 409
    assert EXISTING_ID in fake.projects
    assert fake.deleted == []


def test_delete_an_empty_project_removes_only_the_db_row(world):
    client, fake, _ = world
    fake._pending_count = 0
    r = client.delete(f"/api/projects/{EXISTING_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["drive_kept"] is True
    assert EXISTING_ID not in fake.projects


def test_unknown_project_404s_on_get_patch_and_delete(world):
    client, _, _ = world
    missing = uuid.uuid4()
    assert client.get(f"/api/projects/{missing}").status_code == 404
    assert client.patch(f"/api/projects/{missing}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/projects/{missing}").status_code == 404


# --- ingest defaults new episodes to the default project -----------------------------

class _IngestSession:
    """Enough of a Session for create_episode: every lookup is "not found"."""

    def scalar(self, _query):
        return None

    def add(self, _obj) -> None:
        pass

    def flush(self) -> None:
        pass


def test_upload_with_no_project_id_uses_the_default_project(tmp_path, monkeypatch):
    from app import ingest
    from app.config import settings

    monkeypatch.setattr(settings, "audio_dir", tmp_path)
    monkeypatch.setattr(ingest, "probe_duration_s", lambda path: 12.0)
    default = Project(id=EXISTING_ID, slug="dan-ba-30", name="Đàn bà 30+")
    monkeypatch.setattr("app.projects.default_project", lambda s: default)

    import io

    episode, created = ingest.create_episode(
        _IngestSession(), filename="clip.mp3", fileobj=io.BytesIO(b"fake-audio-bytes"),
    )
    assert created is True
    assert episode.project_id == EXISTING_ID


def test_upload_with_a_project_id_uses_it_instead(tmp_path, monkeypatch):
    from app import ingest
    from app.config import settings

    monkeypatch.setattr(settings, "audio_dir", tmp_path)
    monkeypatch.setattr(ingest, "probe_duration_s", lambda path: 12.0)
    other = uuid.uuid4()

    import io

    episode, _ = ingest.create_episode(
        _IngestSession(), filename="clip.mp3", fileobj=io.BytesIO(b"fake-audio-bytes"),
        project_id=other,
    )
    assert episode.project_id == other
