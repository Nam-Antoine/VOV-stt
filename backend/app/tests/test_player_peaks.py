"""Waveform peaks: right length, right duration, loudness where the loud part is."""

from __future__ import annotations

import numpy as np
import pytest

sf = pytest.importorskip("soundfile")

from app.player import compute_peaks  # noqa: E402


def test_peaks_track_the_signal(tmp_path):
    rate = 16000
    quiet = np.zeros(rate * 2, dtype=np.int16)
    loud = np.full(rate * 2, 16384, dtype=np.int16)   # half scale
    wav = tmp_path / "x.16k.wav"
    sf.write(wav, np.concatenate([quiet, loud]), rate, subtype="PCM_16")

    result = compute_peaks(wav, count=100)

    assert result["duration"] == pytest.approx(4.0)
    peaks = result["peaks"]
    assert len(peaks) == 100
    assert max(peaks[:50]) == 0.0
    assert min(peaks[50:]) == pytest.approx(0.5, abs=1e-3)


def test_empty_audio_has_no_peaks(tmp_path):
    wav = tmp_path / "empty.16k.wav"
    sf.write(wav, np.zeros(0, dtype=np.int16), 16000, subtype="PCM_16")
    assert compute_peaks(wav) == {"duration": 0.0, "peaks": []}
