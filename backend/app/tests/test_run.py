"""One pass: audio → VAD → ASR → utterances → raw JSON, with no speaker information.

These tests pin that the document is verbatim ASR output (CLAUDE.md rule 1) and that
nothing speaker-related is left in it: no ``diarization`` block, no ``speaker`` on words
or utterances.

No native runtime: every sherpa-onnx / ffmpeg stage is monkeypatched.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline import run as run_mod
from app.pipeline.asr import AsrParams
from app.pipeline.audio import AudioInfo
from app.pipeline.vad import VadParams

# Fillers, a repetition and a false start: the document must keep every one.
ASR_WORDS = [
    ("Ờ", 0.10, 0.30), ("thì", 0.30, 0.50), ("thì", 0.50, 0.70), ("em", 0.70, 0.90),
    ("à", 1.00, 1.20), ("ĐÀN", 1.20, 1.50), ("BÀ", 1.50, 1.80),
    ("ừ", 3.00, 3.20), ("chị", 3.20, 3.40), ("ch-", 3.40, 3.50), ("chị", 3.50, 3.80),
]


def _asr_words() -> list[dict]:
    return [{"i": i, "text": t, "start": s, "end": e, "conf": -0.1}
            for i, (t, s, e) in enumerate(ASR_WORDS)]


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    info = AudioInfo(source_path=tmp_path / "ep.m4a", wav_path=tmp_path / "ep.wav",
                     source_sha256="0" * 64, duration_s=4.0, sample_rate=16_000,
                     channels=1)
    monkeypatch.setattr(run_mod.audio_mod, "prepare", lambda *a, **k: info)
    monkeypatch.setattr(run_mod.audio_mod, "read_wav_f32", lambda p: ([0.0] * 10, 16_000))
    monkeypatch.setattr(run_mod, "vad_mod_segment", lambda *a: [(0.0, 2.0), (2.8, 4.0)])
    monkeypatch.setattr(run_mod.asr_mod, "recognizer_from_params", lambda p: object())
    # A fresh list per call, like the real decoder.
    monkeypatch.setattr(run_mod.asr_mod, "transcribe_segments",
                        lambda *a, **k: _asr_words())
    monkeypatch.setattr(run_mod.asr_mod, "engine_block",
                        lambda p, hotwords_sha256=None: {"name": "stub"})
    return SimpleNamespace(
        audio=tmp_path / "ep.m4a",
        kwargs={"asr_params": AsrParams(model_dir="m"), "vad_params": VadParams(),
                "episode_id": "ep-1"},
        work_dir=tmp_path,
    )


def _run(st) -> dict:
    return run_mod.transcribe(st.audio, work_dir=st.work_dir, **st.kwargs)


def test_document_is_verbatim_asr(stubbed):
    doc = _run(stubbed)
    assert [w["text"] for w in doc["words"]] == [t for t, _, _ in ASR_WORDS]
    # Utterance text is a plain join of the words it covers — nothing cleaned.
    joined = " ".join(u["text"] for u in doc["utterances"])
    assert joined == " ".join(t for t, _, _ in ASR_WORDS)
    assert "thì thì" in joined and "ch- chị" in joined


def test_document_has_no_speaker_information(stubbed):
    doc = _run(stubbed)
    assert doc["schema_version"] == 2
    assert "diarization" not in doc and "speakers_pending" not in doc
    assert all("speaker" not in w for w in doc["words"])
    assert all("speaker" not in u for u in doc["utterances"])
    assert set(doc["timing"]["stages_s"]) == {"audio", "vad", "asr", "group"}


def test_utterances_split_on_pauses_only(stubbed):
    doc = _run(stubbed)
    # 1.8 -> 3.0 is the only gap over 0.5 s.
    assert [u["text"] for u in doc["utterances"]] == ["Ờ thì thì em à ĐÀN BÀ", "ừ chị ch- chị"]


def test_migration_revision_fits_alembic_version_column():
    # alembic_version.version_num is VARCHAR(32); a longer id fails at upgrade time.
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    for path in versions.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("revision = "):
                assert len(line.split('"')[1]) <= 32, path.name
