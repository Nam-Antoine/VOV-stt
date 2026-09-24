"""Speaker diarization over the whole file (PLAN §3).

    segmentation: pyannote/segmentation-3.0 ONNX
    embedding:    3D-Speaker or WeSpeaker ONNX
    clustering:   num_clusters=0 (auto), threshold tuned in the pilot

Runs **after** ASR, not concurrently — it is the slow stage (~5–10× realtime) and the box
has 4 vCPU (PLAN §3). Diarization touches no text; it only produces speaker spans.

Overlapping speech (expected in the vox-pop montages) is not solved by any engine. The
merge step assigns the dominant speaker and the UI lets a verifier split or relabel.
PLAN §3: do not tune around it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiarParams:
    """PLAN §3 defaults; ``threshold`` is swept 0.5–0.9 in the pilot (§4.3)."""

    segmentation_model: str
    embedding_model: str
    threshold: float = 0.8
    #: 0 means "let the clustering decide" (PLAN §5). sherpa-onnx spells that -1.
    num_clusters: int = 0
    min_duration_on: float = 0.3
    min_duration_off: float = 0.5
    #: Step of pyannote's 10 s sliding window as a fraction of the window. sherpa-onnx
    #: defaults to 0.1 (1 s step); every step yields speaker embeddings, which are most
    #: of diarization's cost. 0.2 halves the work: on the 14-minute VOV episode 147 s →
    #: 71 s with 99.1 % of speech time keeping the same speaker. 0.3 was 3.1x faster but
    #: moved ~5 % of speech to a different cluster, so it is not the default.
    window_shift_ratio: float = 0.2
    num_threads: int = 3

    def as_json(self) -> dict:
        """The ``diarization`` block of the raw JSON, minus ``segments`` (PLAN §5)."""
        return {
            "segmentation": self.segmentation_model.rsplit("/", 1)[-1],
            "embedding": self.embedding_model.rsplit("/", 1)[-1],
            "threshold": self.threshold,
            "num_clusters": self.num_clusters,
            "min_duration_on": self.min_duration_on,
            "min_duration_off": self.min_duration_off,
            "window_shift_ratio": self.window_shift_ratio,
        }


def build_diarizer(params: DiarParams):
    """Construct a ``sherpa_onnx.OfflineSpeakerDiarization``.

    Imported lazily: the pure-python merge logic and its tests must not need the native
    runtime.
    """
    import sherpa_onnx

    pyannote = sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
        model=params.segmentation_model
    )
    pyannote.window_shift_ratio = params.window_shift_ratio

    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=pyannote,
            num_threads=params.num_threads,
            provider="cpu",
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=params.embedding_model,
            num_threads=params.num_threads,
            provider="cpu",
        ),
        clustering=sherpa_onnx.FastClusteringConfig(
            # sherpa-onnx uses -1 for "auto"; PLAN §5 writes that as 0.
            num_clusters=params.num_clusters if params.num_clusters > 0 else -1,
            threshold=params.threshold,
        ),
        min_duration_on=params.min_duration_on,
        min_duration_off=params.min_duration_off,
    )
    if not cfg.validate():
        raise RuntimeError(
            "invalid diarization config — check that "
            f"{params.segmentation_model!r} and {params.embedding_model!r} exist "
            "(run `make models`)"
        )
    return sherpa_onnx.OfflineSpeakerDiarization(cfg)


def diarize(samples: np.ndarray, sample_rate: int, params: DiarParams,
            *, progress=None) -> list[dict]:
    """Return ``[{"start": s, "end": s, "speaker": int}, …]`` sorted by start time."""
    sd = build_diarizer(params)
    if sd.sample_rate != sample_rate:
        raise ValueError(
            f"diarization model expects {sd.sample_rate} Hz, got {sample_rate} Hz"
        )

    callback = None
    if progress is not None:
        def callback(done, total):  # noqa: ANN001 — sherpa-onnx calls this
            progress(done, total)
            return 0

    result = sd.process(samples, callback=callback)
    segments = [
        {"start": float(s.start), "end": float(s.end), "speaker": int(s.speaker)}
        for s in result.sort_by_start_time()
    ]
    speakers = {s["speaker"] for s in segments}
    log.info("diarization: %d segments, %d speaker clusters", len(segments), len(speakers))
    if len(speakers) > 12:
        log.warning(
            "%d clusters is a lot — vox-pop montages always look like this. Raise "
            "DIAR_THRESHOLD or min_duration_on, but PLAN §13 says flag it rather than "
            "tune forever.",
            len(speakers),
        )
    return segments
