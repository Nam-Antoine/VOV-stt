"""purge_audio: audio goes only when the Doc is safe, and only this episode's files."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app import purge_audio
from app.config import settings


class _Session:
    """Answers the pending-job query; nothing else touches the database here."""

    def __init__(self, pending=None) -> None:
        self.pending = pending

    def scalar(self, _stmt):
        return self.pending

    def flush(self) -> None:
        pass


@pytest.fixture
def episode(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    audio = tmp_path / "audio"
    cache = tmp_path / "cache" / "player"
    audio.mkdir()
    cache.mkdir(parents=True)
    for name in ("ep.mp3", "ep.16k.flac", "ep.16k.wav", "ep-2.mp3", "ep-2.16k.flac"):
        (audio / name).write_bytes(b"x" * 10)
    for name in ("ep.16k-10-1.m4a", "ep.16k-10-1.peaks.json", "ep-2.16k-10-1.m4a"):
        (cache / name).write_bytes(b"x" * 10)
    return SimpleNamespace(id=uuid.uuid4(), slug="ep", audio_path=str(audio / "ep.mp3"))


def _names(tmp_path):
    return sorted(p.name for p in tmp_path.rglob("*") if p.is_file())


def test_audio_files_are_only_this_episodes(episode, tmp_path):
    names = sorted(p.name for p in purge_audio.audio_files(episode))
    assert names == ["ep.16k-10-1.m4a", "ep.16k-10-1.peaks.json", "ep.16k.flac",
                     "ep.16k.wav", "ep.mp3"]


def test_purges_when_doc_is_current(episode, tmp_path, monkeypatch):
    monkeypatch.setattr(purge_audio, "_doc_is_current", lambda s, e: None)
    out = purge_audio.purge_episode(_Session(), episode)
    assert out.purged and out.freed_bytes == 50
    assert episode.audio_path is None
    assert _names(tmp_path) == ["ep-2.16k-10-1.m4a", "ep-2.16k.flac", "ep-2.mp3"]


def test_dry_run_deletes_nothing(episode, tmp_path, monkeypatch):
    monkeypatch.setattr(purge_audio, "_doc_is_current", lambda s, e: None)
    before = _names(tmp_path)
    out = purge_audio.purge_episode(_Session(), episode, dry_run=True)
    assert out.purged and out.freed_bytes == 50
    assert _names(tmp_path) == before and episode.audio_path


@pytest.mark.parametrize("pending, doc_reason", [
    (uuid.uuid4(), None),                      # a job still waits on the episode
    (None, "Doc is behind the current text"),  # sync pending
    (None, "no Google Doc yet"),
])
def test_keeps_audio_when_not_safe(episode, tmp_path, monkeypatch, pending, doc_reason):
    monkeypatch.setattr(purge_audio, "_doc_is_current", lambda s, e: doc_reason)
    before = _names(tmp_path)
    out = purge_audio.purge_episode(_Session(pending), episode)
    assert not out.purged
    assert _names(tmp_path) == before and episode.audio_path


def test_keeps_audio_when_drive_doubts_the_doc(episode, tmp_path, monkeypatch):
    monkeypatch.setattr(purge_audio, "_doc_is_current", lambda s, e: None)
    monkeypatch.setattr(purge_audio, "_doc_in_drive", lambda g, d: "Doc is in the Drive trash")
    out = purge_audio.purge_episode(_Session(), episode, g=object())
    assert not out.purged and out.reason == "Doc is in the Drive trash"
    assert episode.audio_path


def test_worker_hook_is_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "purge_audio_after_sync", False)
    assert purge_audio.purge_after_sync(_Session(), {"id": 1, "episode_id": uuid.uuid4()}) is None
