"""Silero VAD segmentation (PLAN §3).

    Silero VAD → pad 0.35 s both sides → merge if gap < 0.3 s → hard-split > 25 s
    at the lowest-energy point.

**VAD must never drop speech.** Short isolated fillers ("à", "ừ") are exactly what an
aggressive VAD eats, and those fillers are the corpus. Hence threshold ≈ 0.3, generous
padding, and :func:`speech_ratio` logging: if detected speech is under 70 % of a radio
talk show's duration, the VAD is too aggressive and the threshold must come down.

Segments are ``(start_s, end_s)`` pairs in seconds, absolute against the 16 kHz WAV.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

Segment = tuple[float, float]


@dataclass(frozen=True)
class VadParams:
    """PLAN §3 defaults. The pilot (§4.3) sweeps ``threshold`` ∈ {0.2, 0.3, 0.5}."""

    model: str = ""
    threshold: float = 0.3
    min_speech_s: float = 0.1
    min_silence_s: float = 0.4
    pad_s: float = 0.35
    merge_gap_s: float = 0.3
    max_segment_s: float = 25.0
    min_speech_ratio: float = 0.70
    num_threads: int = 1
    sample_rate: int = 16_000

    def as_json(self) -> dict:
        """The ``vad`` block of the raw JSON, minus ``segments``."""
        return {
            "model": self.model.rsplit("/", 1)[-1] or "silero_vad.onnx",
            "threshold": self.threshold,
            "min_silence_s": self.min_silence_s,
            "pad_s": self.pad_s,
        }


def build_vad(params: VadParams, *, buffer_size_s: float | None = None):
    """Construct a ``sherpa_onnx.VoiceActivityDetector``.

    Imported lazily so that the pure-python parts of the pipeline (and the unit tests)
    do not need the native runtime installed.
    """
    import sherpa_onnx

    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = params.model
    cfg.silero_vad.threshold = params.threshold
    cfg.silero_vad.min_speech_duration = params.min_speech_s
    cfg.silero_vad.min_silence_duration = params.min_silence_s
    # Silero's own cap is deliberately loose: it cuts at a fixed length, whereas
    # `hard_split` cuts at the quietest frame. Leave the real capping to hard_split and
    # only use this as a backstop that keeps a segment inside the VAD's ring buffer.
    cfg.silero_vad.max_speech_duration = float(params.max_segment_s) * 2.0
    cfg.sample_rate = params.sample_rate
    cfg.num_threads = params.num_threads
    cfg.provider = "cpu"
    if not cfg.validate():
        raise RuntimeError(f"invalid VAD config (model={params.model!r})")
    # The ring buffer must hold the longest segment Silero will emit, plus headroom.
    buffer_s = buffer_size_s or max(60.0, params.max_segment_s * 3.0)
    return sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=buffer_s)


def raw_segments(samples: np.ndarray, params: VadParams,
                 *, window: int = 8_000) -> list[Segment]:
    """Run Silero over ``samples`` and return the raw speech spans, unpadded."""
    vad = build_vad(params)
    sr = params.sample_rate
    out: list[Segment] = []
    for offset in range(0, len(samples), window):
        vad.accept_waveform(samples[offset:offset + window])
        while not vad.empty():
            seg = vad.front
            start = seg.start / sr
            out.append((start, start + len(seg.samples) / sr))
            vad.pop()
    vad.flush()
    while not vad.empty():
        seg = vad.front
        start = seg.start / sr
        out.append((start, start + len(seg.samples) / sr))
        vad.pop()
    return out


def pad_and_merge(segments: list[Segment], params: VadParams,
                  duration_s: float) -> list[Segment]:
    """Pad each span by ``pad_s`` both sides, then merge spans closer than ``merge_gap_s``.

    Padding is deliberate over-capture: a filler clipped at a segment boundary is a lost
    token, whereas a little extra silence costs nothing.
    """
    if not segments:
        return []
    padded = [
        (max(0.0, s - params.pad_s), min(duration_s, e + params.pad_s))
        for s, e in sorted(segments)
    ]
    merged: list[Segment] = [padded[0]]
    for start, end in padded[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end < params.merge_gap_s:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def lowest_energy_split(samples: np.ndarray, start_s: float, end_s: float,
                        sample_rate: int, *, guard_s: float = 2.0,
                        frame_s: float = 0.05) -> float:
    """Return the time of the quietest frame inside ``(start_s, end_s)``.

    ``guard_s`` keeps the cut away from the edges so we never produce a sliver segment.
    Falls back to the midpoint when the span is too short to search.
    """
    lo = start_s + guard_s
    hi = end_s - guard_s
    if hi <= lo:
        return (start_s + end_s) / 2.0
    i0, i1 = int(lo * sample_rate), int(hi * sample_rate)
    window = samples[i0:i1]
    if window.size == 0:
        return (start_s + end_s) / 2.0
    frame = max(1, int(frame_s * sample_rate))
    n = window.size // frame
    if n == 0:
        return (start_s + end_s) / 2.0
    energy = np.abs(window[: n * frame].reshape(n, frame)).mean(axis=1)
    return lo + (int(energy.argmin()) + 0.5) * frame_s


def hard_split(segments: list[Segment], samples: np.ndarray, params: VadParams,
               sample_rate: int) -> list[Segment]:
    """Recursively split any segment longer than ``max_segment_s``.

    PLAN §3: non-streaming Zipformer memory grows with input length; segments ≤ 25 s are
    how sherpa-onnx is meant to be driven over long audio. No audio is discarded — a
    split produces two adjacent segments that still cover the whole span.
    """
    out: list[Segment] = []
    queue = list(segments)
    while queue:
        start, end = queue.pop(0)
        if end - start <= params.max_segment_s:
            out.append((start, end))
            continue
        cut = lowest_energy_split(samples, start, end, sample_rate)
        if not (start < cut < end):
            cut = (start + end) / 2.0
        queue.insert(0, (cut, end))
        queue.insert(0, (start, cut))
    return sorted(out)


def speech_ratio(segments: list[Segment], duration_s: float) -> float:
    """Fraction of the file covered by speech segments (segments may not overlap)."""
    if duration_s <= 0:
        return 0.0
    return sum(e - s for s, e in segments) / duration_s


def segment(samples: np.ndarray, sample_rate: int, params: VadParams) -> list[Segment]:
    """Full VAD stage: detect → pad+merge → hard-split, with a coverage warning."""
    duration_s = len(samples) / sample_rate
    spans = raw_segments(samples, params)
    spans = pad_and_merge(spans, params, duration_s)
    spans = hard_split(spans, samples, params, sample_rate)

    ratio = speech_ratio(spans, duration_s)
    log.info(
        "VAD: %d segments, %.1f s speech of %.1f s (%.0f%% coverage)",
        len(spans), ratio * duration_s, duration_s, ratio * 100,
    )
    if ratio < params.min_speech_ratio:
        log.warning(
            "VAD coverage %.0f%% is below %.0f%% — the VAD is probably eating short "
            "fillers. Lower VAD_THRESHOLD (PLAN §3) and re-run before trusting this "
            "transcript.",
            ratio * 100, params.min_speech_ratio * 100,
        )
    return spans


def slice_samples(samples: np.ndarray, start_s: float, end_s: float,
                  sample_rate: int) -> np.ndarray:
    """Samples for one segment, clamped to the array bounds."""
    i0 = max(0, int(round(start_s * sample_rate)))
    i1 = min(len(samples), int(round(end_s * sample_rate)))
    return samples[i0:i1]
