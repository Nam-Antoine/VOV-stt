"""Text first: the ASR-only preview and the final run must agree word for word.

The worker publishes :func:`run.preliminary_doc` as soon as ASR finishes and builds the
final document from the same :class:`run.AsrStage` after diarization. These tests pin
the three promises that design makes:

* the preview is verbatim ASR output (CLAUDE.md rule 1) with every speaker ``-1``;
* building the preview does not disturb the words the final document is built from,
  so a two-phase run is identical to the one-shot run;
* edits against a speakers-pending transcript are refused, never stranded.

No native runtime: every sherpa-onnx / ffmpeg stage is monkeypatched.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline import run as run_mod
from app.pipeline.asr import AsrParams
from app.pipeline.audio import AudioInfo
from app.pipeline.diarize import DiarParams
from app.pipeline.vad import VadParams

# Fillers, a repetition and a false start: the preview must keep every one.
ASR_WORDS = [
    ("Ờ", 0.10, 0.30), ("thì", 0.30, 0.50), ("thì", 0.50, 0.70), ("em", 0.70, 0.90),
    ("à", 1.00, 1.20), ("ĐÀN", 1.20, 1.50), ("BÀ", 1.50, 1.80),
    ("ừ", 3.00, 3.20), ("chị", 3.20, 3.40), ("ch-", 3.40, 3.50), ("chị", 3.50, 3.80),
]
DIAR_SEGMENTS = [
    {"start": 0.0, "end": 2.0, "speaker": 0},
    {"start": 2.8, "end": 4.0, "speaker": 1},
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
    monkeypatch.setattr(run_mod.diarize_mod, "diarize",
                        lambda *a, **k: [dict(s) for s in DIAR_SEGMENTS])
    return SimpleNamespace(
        audio=tmp_path / "ep.m4a",
        kwargs={"asr_params": AsrParams(model_dir="m"), "vad_params": VadParams(),
                "episode_id": "ep-1"},
        diar=DiarParams(segmentation_model="seg.onnx", embedding_model="emb.onnx"),
        work_dir=tmp_path,
    )


def _stage(st):
    return run_mod.run_asr(st.audio, work_dir=st.work_dir,
                           asr_params=st.kwargs["asr_params"],
                           vad_params=st.kwargs["vad_params"])


def _comparable(doc: dict) -> dict:
    """Drop what legitimately differs between two runs: wall clock and timestamps."""
    return {k: v for k, v in doc.items() if k not in ("timing", "created_at")}


def test_preview_is_verbatim_asr_with_unknown_speakers(stubbed):
    doc = run_mod.preliminary_doc(_stage(stubbed), **stubbed.kwargs)

    assert doc["speakers_pending"] is True
    assert doc["diarization"] is None
    assert [w["text"] for w in doc["words"]] == [t for t, _, _ in ASR_WORDS]
    assert {w["speaker"] for w in doc["words"]} == {-1}
    assert {u["speaker"] for u in doc["utterances"]} == {-1}
    # Utterance text is a plain join of the words it covers — nothing cleaned.
    joined = " ".join(u["text"] for u in doc["utterances"])
    assert joined == " ".join(t for t, _, _ in ASR_WORDS)
    assert "thì thì" in joined and "ch- chị" in joined
    assert set(doc["timing"]["stages_s"]) == {"audio", "vad", "asr"}


def test_two_phase_run_equals_one_shot_run(stubbed):
    one_shot = run_mod.transcribe(stubbed.audio, work_dir=stubbed.work_dir,
                                  diar_params=stubbed.diar, **stubbed.kwargs)

    stage = _stage(stubbed)
    run_mod.preliminary_doc(stage, **stubbed.kwargs)   # must not touch stage.words
    assert {w.get("speaker") for w in stage.words} == {None}
    final = run_mod.finish(stage, diar_params=stubbed.diar, **stubbed.kwargs)

    assert _comparable(final) == _comparable(one_shot)
    assert "speakers_pending" not in final
    assert {w["speaker"] for w in final["words"]} == {0, 1}
    assert set(final["timing"]["stages_s"]) == {"audio", "vad", "asr", "diarize", "merge"}


def test_preview_and_final_share_every_word(stubbed):
    stage = _stage(stubbed)
    preview = run_mod.preliminary_doc(stage, **stubbed.kwargs)
    final = run_mod.finish(stage, diar_params=stubbed.diar, **stubbed.kwargs)

    strip = [{k: w[k] for k in ("i", "text", "start", "end", "conf")} for w in preview["words"]]
    assert strip == [{k: w[k] for k in ("i", "text", "start", "end", "conf")}
                     for w in final["words"]]


def test_edits_refused_while_speakers_pending():
    from fastapi import HTTPException

    from app.api.utterances import SPEAKERS_PENDING_DETAIL, ensure_editable

    with pytest.raises(HTTPException) as exc:
        ensure_editable(SimpleNamespace(speakers_pending=True))
    assert exc.value.status_code == 409
    assert exc.value.detail == SPEAKERS_PENDING_DETAIL

    ensure_editable(SimpleNamespace(speakers_pending=False))
    ensure_editable(None)


def test_migration_revision_fits_alembic_version_column():
    # alembic_version.version_num is VARCHAR(32); a longer id fails at upgrade time.
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    for path in versions.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("revision = "):
                assert len(line.split('"')[1]) <= 32, path.name


def test_diarization_window_shift_is_recorded_in_raw_json():
    # The knob changes speaker labels slightly, so every raw JSON must say which it used.
    params = DiarParams(segmentation_model="seg.onnx", embedding_model="emb.onnx")
    assert params.window_shift_ratio == 0.2
    assert params.as_json()["window_shift_ratio"] == 0.2


class _Rows:
    """Just enough Session for withdraw_preliminary: rows by id, flush/commit counted."""

    def __init__(self, *rows):
        self.rows = {r.id: r for r in rows}
        self.commits = 0

    def get(self, model, key):
        return self.rows.get(key)

    def flush(self):
        assert sum(r.is_current for r in self.rows.values()) <= 1, "two current rows"

    def commit(self):
        self.flush()
        self.commits += 1


def _row(id_, current, pending=False):
    return SimpleNamespace(id=id_, is_current=current, speakers_pending=pending)


def test_failed_diarization_restores_the_previous_transcript():
    from app.worker import withdraw_preliminary

    old, preview = _row("old", False), _row("new", True, pending=True)
    session = _Rows(old, preview)
    withdraw_preliminary(session, "new", "old")
    assert old.is_current and not preview.is_current
    assert session.commits == 1


def test_failed_diarization_on_a_first_run_unlocks_the_preview():
    from app.worker import withdraw_preliminary

    preview = _row("new", True, pending=True)
    withdraw_preliminary(_Rows(preview), "new", None)
    assert preview.is_current and not preview.speakers_pending
