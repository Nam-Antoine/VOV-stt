"""The 16 kHz decode is FLAC now, and must hold exactly the samples a WAV would."""

from __future__ import annotations

import shutil
import subprocess

import numpy as np
import pytest

sf = pytest.importorskip("soundfile")

from app.pipeline import audio as audio_mod  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@needs_ffmpeg
def test_flac_holds_the_same_samples_as_wav(tmp_path):
    src = tmp_path / "ep.mp3"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=f=440:d=2:sample_rate=44100", "-ac", "2", str(src)],
        check=True,
    )
    wav = tmp_path / "ep.16k.wav"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000",
         "-acodec", "pcm_s16le", "-f", "wav", str(wav)],
        check=True,
    )
    info = audio_mod.prepare(src, tmp_path)
    assert info.wav_path.name == "ep.16k.flac"
    flac, rate = audio_mod.read_pcm_f32(info.wav_path)
    ref, ref_rate = audio_mod.read_pcm_f32(wav)
    assert rate == ref_rate == 16_000
    assert np.array_equal(flac, ref)


def test_derived_path_prefers_flac_then_legacy_wav(tmp_path):
    original = tmp_path / "ep.mp3"
    original.touch()
    assert audio_mod.derived_path(original) is None
    (tmp_path / "ep.16k.wav").touch()
    assert audio_mod.derived_path(original).name == "ep.16k.wav"
    (tmp_path / "ep.16k.flac").touch()
    assert audio_mod.derived_path(original).name == "ep.16k.flac"
    assert audio_mod.is_derived(tmp_path / "ep.16k.flac")
    assert not audio_mod.is_derived(original)
