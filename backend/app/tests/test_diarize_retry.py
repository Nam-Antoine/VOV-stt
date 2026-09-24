"""The one-shot retry at a lower threshold when host and guest merge into one cluster."""

import numpy as np
import pytest

from app.pipeline import diarize as dz

PARAMS = dz.DiarParams(segmentation_model="seg.onnx", embedding_model="emb.onnx",
                       threshold=0.8)


def segs(*shares):
    """One segment per cluster, lengths proportional to ``shares``."""
    out, t = [], 0.0
    for spk, share in enumerate(shares):
        out.append({"start": t, "end": t + share * 100, "speaker": spk})
        t += share * 100
    return out


@pytest.fixture
def fake(monkeypatch):
    by_threshold = {}
    calls = []

    def fake_diarize(samples, sr, params, progress=None):
        calls.append(params.threshold)
        return by_threshold[params.threshold]

    monkeypatch.setattr(dz, "diarize", fake_diarize)
    return by_threshold, calls


def run():
    return dz.diarize_adaptive(np.zeros(1, dtype=np.float32), 16000, PARAMS)


def test_balanced_episode_runs_once(fake):
    by, calls = fake
    by[0.8] = segs(0.56, 0.20, 0.24)
    out, used, retry = run()
    assert calls == [0.8] and used.threshold == 0.8 and retry is None


def test_merged_voices_are_split_by_the_retry(fake):
    by, calls = fake
    by[0.8] = segs(0.80, 0.07, 0.13)
    by[0.7] = segs(0.51, 0.30, 0.19)
    out, used, retry = run()
    assert calls == [0.8, 0.7]
    assert out == by[0.7] and used.threshold == 0.7
    assert retry["kept"] and retry["from_threshold"] == 0.8
    assert retry["tried"] == {"0.7": 0.51}


def test_monologue_keeps_the_first_result(fake):
    by, calls = fake
    by[0.8] = segs(0.85, 0.15)
    by[0.7] = segs(0.80, 0.10, 0.10)
    by[0.6] = segs(0.78, 0.12, 0.10)
    out, used, retry = run()
    assert calls == [0.8, 0.7, 0.6]
    assert out == by[0.8] and used.threshold == 0.8 and retry["kept"] is False


def test_steps_down_until_voices_separate(fake):
    by, calls = fake
    by[0.8] = segs(0.80, 0.09, 0.11)
    by[0.7] = segs(0.77, 0.09, 0.14)
    by[0.6] = segs(0.53, 0.23, 0.24)
    out, used, retry = run()
    assert calls == [0.8, 0.7, 0.6]
    assert out == by[0.6] and used.threshold == 0.6
    assert retry["tried"] == {"0.7": 0.77, "0.6": 0.53}


def test_missing_guest_triggers_retry_below_the_dominant_share(fake):
    by, calls = fake
    by[0.8] = segs(0.70, 0.09, 0.08, 0.08, 0.05)
    by[0.7] = segs(0.70, 0.09, 0.08, 0.08, 0.05)
    by[0.6] = segs(0.45, 0.25, 0.09, 0.08, 0.13)
    out, used, retry = run()
    assert calls == [0.8, 0.7, 0.6] and used.threshold == 0.6


def test_talkative_guest_beside_a_real_host_is_left_alone(fake):
    by, calls = fake
    by[0.8] = segs(0.71, 0.14, 0.15)
    out, used, retry = run()
    assert calls == [0.8] and retry is None


def test_top_share_empty():
    assert dz.top_share([]) == 0.0
