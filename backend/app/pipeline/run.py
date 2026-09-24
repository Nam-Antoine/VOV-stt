"""Transcribe one episode end-to-end and write the raw JSON (PLAN §3, §5).

    python -m app.pipeline.run --audio x.mp3 --out x.json

Stages: ffmpeg → Silero VAD → Zipformer ASR per segment → diarization over the whole
file → merge → raw JSON. ASR runs sequentially on one process (PLAN §3); diarization
runs after ASR, never alongside it.

The JSON this writes is the **immutable master record** (PLAN §0.2). It is written once;
a re-run produces a new file, never an edit of an existing one. ``--out`` refuses to
overwrite unless ``--force`` is given.

Prints a realtime factor and peak RSS at the end. PLAN §11 T1: the run must stay under
2 GB RSS on the 6 GB box.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import resource
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import asr as asr_mod
from . import audio as audio_mod
from . import diarize as diarize_mod
from . import merge as merge_mod
from .asr import AsrParams
from .diarize import DiarParams
from .vad import VadParams

log = logging.getLogger("pipeline.run")

SCHEMA_VERSION = 1


def peak_rss_mb() -> float:
    """Peak resident set size of this process, in MiB (Linux reports KiB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


class Stopwatch:
    """Per-stage wall-clock timing, for the RTF report."""

    def __init__(self) -> None:
        self.stages: dict[str, float] = {}
        self._t0 = time.perf_counter()

    def mark(self, name: str) -> float:
        now = time.perf_counter()
        self.stages[name] = now - self._t0
        self._t0 = now
        return self.stages[name]

    def resume(self) -> None:
        """Restart the clock without recording a stage (e.g. after an I/O pause)."""
        self._t0 = time.perf_counter()

    @property
    def total_s(self) -> float:
        return sum(self.stages.values())


@dataclass
class AsrStage:
    """Everything the ASR phase produced, held in memory until diarization finishes.

    The worker publishes a speakers-pending transcript from this (:func:`preliminary_doc`)
    and then hands the same object to :func:`finish`, so the final document is built
    from exactly the words the preliminary one showed — ASR is never run twice.
    """

    info: audio_mod.AudioInfo
    samples: object          # np.ndarray; kept untyped so tests need no numpy import
    sample_rate: int
    segments: list[tuple[float, float]]
    words: list[dict]
    watch: Stopwatch


def run_asr(audio_path: Path, *, work_dir: Path, asr_params: AsrParams,
            vad_params: VadParams) -> AsrStage:
    """Stages audio → VAD → ASR. Seconds to a minute on a 14-minute episode."""
    watch = Stopwatch()

    log.info("audio: decoding %s to 16 kHz mono", audio_path)
    info = audio_mod.prepare(audio_path, work_dir)
    samples, sample_rate = audio_mod.read_wav_f32(info.wav_path)
    watch.mark("audio")
    log.info("audio: %.1f s at %d Hz -> %s", info.duration_s, sample_rate, info.wav_path)

    log.info("vad: segmenting")
    segments = vad_mod_segment(samples, sample_rate, vad_params)
    watch.mark("vad")

    log.info("asr: decoding %d segments", len(segments))
    rec = asr_mod.recognizer_from_params(asr_params)

    def asr_progress(done: int, total: int) -> None:
        if done == total or done % 25 == 0:
            log.info("asr: %d/%d segments", done, total)

    words = asr_mod.transcribe_segments(
        rec, samples, segments, sample_rate=sample_rate, progress=asr_progress
    )
    watch.mark("asr")
    log.info("asr: %d words", len(words))
    return AsrStage(info=info, samples=samples, sample_rate=sample_rate,
                    segments=segments, words=words, watch=watch)


def _document(stage: AsrStage, words: list[dict], utterances: list[dict], *,
              asr_params: AsrParams, vad_params: VadParams, diarization: dict | None,
              source_url: str | None, episode_id: str | None,
              hotwords_sha256: str | None) -> dict:
    """The PLAN §5 raw JSON document, from a finished (or ASR-only) run."""
    info, watch = stage.info, stage.watch
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id or str(uuid.uuid4()),
        "source": info.as_source_block(source_url),
        "audio": info.as_audio_block(),
        "engine": asr_mod.engine_block(asr_params, hotwords_sha256=hotwords_sha256),
        "vad": {**vad_params.as_json(),
                "segments": [[round(s, 3), round(e, 3)] for s, e in stage.segments]},
        "diarization": diarization,
        "words": [
            {
                "i": w["i"], "text": w["text"],
                "start": round(float(w["start"]), 3),
                "end": round(float(w["end"]), 3) if w.get("end") is not None else None,
                "conf": w.get("conf"),
                "speaker": w.get("speaker", merge_mod.UNKNOWN_SPEAKER),
            }
            for w in words
        ],
        "utterances": utterances,
        "created_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        "timing": {
            "stages_s": {k: round(v, 2) for k, v in watch.stages.items()},
            "total_s": round(watch.total_s, 2),
            "realtime_factor": round(info.duration_s / watch.total_s, 2)
            if watch.total_s else None,
            "peak_rss_mb": round(peak_rss_mb(), 1),
        },
    }


def preliminary_doc(stage: AsrStage, *, asr_params: AsrParams, vad_params: VadParams,
                    source_url: str | None = None, episode_id: str | None = None,
                    hotwords_sha256: str | None = None) -> dict:
    """An ASR-only document to show while diarization runs.

    It is a complete raw JSON in its own right — same words, same text, every speaker
    ``-1`` exactly as a ``--no-diarize`` run — plus ``"speakers_pending": true`` so
    nothing downstream mistakes it for a finished run. Written to its own file: the
    final run gets a new file and a new transcript row, never an edit of this one
    (PLAN §0.2).

    The words are copied: :func:`merge.merge` assigns speakers in place, and the final
    document must be built from untouched ASR output.
    """
    words = copy.deepcopy(stage.words)
    words, utterances = merge_mod.merge(words, [])
    doc = _document(stage, words, utterances, asr_params=asr_params,
                    vad_params=vad_params, diarization=None, source_url=source_url,
                    episode_id=episode_id, hotwords_sha256=hotwords_sha256)
    doc["speakers_pending"] = True
    return doc


def finish(stage: AsrStage, *, asr_params: AsrParams, vad_params: VadParams,
           diar_params: DiarParams | None, source_url: str | None = None,
           episode_id: str | None = None, hotwords_sha256: str | None = None) -> dict:
    """Stages diarize → merge, and the final raw JSON document."""
    watch = stage.watch
    # Time spent publishing the preliminary transcript is not diarization time.
    watch.resume()

    diar_segments: list[dict] = []
    diar_retry: dict | None = None
    if diar_params is not None:
        log.info("diarize: running (this is the slow stage)")

        def diar_progress(done: int, total: int) -> None:
            if total and (done == total or done % max(1, total // 10) == 0):
                log.info("diarize: %d%%", int(100 * done / total))

        diar_segments, diar_params, diar_retry = diarize_mod.diarize_adaptive(
            stage.samples, stage.sample_rate, diar_params, progress=diar_progress
        )
    else:
        log.warning("diarize: skipped (--no-diarize); every word gets speaker -1")
    watch.mark("diarize")

    # VAD segment edges are the pauses a speaker change should sit on.
    pauses = sorted({t for seg in stage.segments for t in seg})
    words, utterances = merge_mod.merge(stage.words, diar_segments, pauses=pauses)
    watch.mark("merge")

    return _document(
        stage, words, utterances, asr_params=asr_params, vad_params=vad_params,
        diarization=(
            {**diar_params.as_json(), "snap_to_vad_s": merge_mod.DEFAULT_SNAP_S,
             **({"retry": diar_retry} if diar_retry else {}),
             "segments": diar_segments}
            if diar_params is not None else None
        ),
        source_url=source_url, episode_id=episode_id, hotwords_sha256=hotwords_sha256,
    )


def transcribe(
    audio_path: Path,
    *,
    work_dir: Path,
    asr_params: AsrParams,
    vad_params: VadParams,
    diar_params: DiarParams | None,
    source_url: str | None = None,
    episode_id: str | None = None,
    hotwords_sha256: str | None = None,
) -> dict:
    """Run every stage and return the raw JSON document (PLAN §5 schema)."""
    stage = run_asr(audio_path, work_dir=work_dir, asr_params=asr_params,
                    vad_params=vad_params)
    return finish(stage, asr_params=asr_params, vad_params=vad_params,
                  diar_params=diar_params, source_url=source_url,
                  episode_id=episode_id, hotwords_sha256=hotwords_sha256)


def vad_mod_segment(samples, sample_rate, vad_params):
    """Indirection so tests can monkeypatch the VAD stage without a model file."""
    from . import vad as vad_mod

    return vad_mod.segment(samples, sample_rate, vad_params)


def write_raw_json(doc: dict, out: Path, *, force: bool = False) -> Path:
    """Write the raw JSON. UTF-8, ``ensure_ascii=False`` (CLAUDE.md rule 3).

    Refuses to overwrite: the raw JSON is immutable (PLAN §0.2).
    """
    out = Path(out)
    if out.exists() and not force:
        raise FileExistsError(
            f"{out} exists. The raw JSON is immutable (PLAN §0.2) — write a new file, "
            "or pass --force if you are certain this one is disposable."
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return out


def report(doc: dict, out: Path) -> str:
    """The end-of-run summary: RTF, peak RSS, and the verbatim sanity numbers."""
    t = doc["timing"]
    dur = doc["audio"]["duration_s"]
    speech_s = sum(e - s for s, e in doc["vad"]["segments"])
    n_speakers = len({s["speaker"] for s in (doc["diarization"] or {}).get("segments", [])})
    lines = [
        "",
        "─" * 66,
        f"  audio            {dur:8.1f} s   ({dur / 60:.1f} min)",
        f"  vad speech       {speech_s:8.1f} s   ({100 * speech_s / dur:.0f}% coverage, "
        f"{len(doc['vad']['segments'])} segments)",
        f"  words            {len(doc['words']):8d}",
        f"  utterances       {len(doc['utterances']):8d}",
        f"  speaker clusters {n_speakers:8d}",
        "  " + "-" * 62,
    ]
    for name, secs in t["stages_s"].items():
        rtf = dur / secs if secs else float("inf")
        lines.append(f"  {name:<16} {secs:8.1f} s   ({rtf:.1f}x realtime)")
    lines += [
        "  " + "-" * 62,
        f"  total            {t['total_s']:8.1f} s   "
        f"({t['realtime_factor']}x realtime)",
        f"  peak RSS         {t['peak_rss_mb']:8.1f} MB  "
        f"({'OK' if t['peak_rss_mb'] < 2048 else 'OVER the 2 GB T1 budget'})",
        f"  raw JSON         {out}",
        "─" * 66,
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m app.pipeline.run",
        description="Transcribe one episode end-to-end and write the raw JSON (PLAN §5).",
    )
    ap.add_argument("--audio", required=True, type=Path, help="source mp3/m4a/wav")
    ap.add_argument("--out", required=True, type=Path, help="raw JSON destination")
    ap.add_argument("--force", action="store_true",
                    help="overwrite --out (the raw JSON is normally immutable)")
    ap.add_argument("--models", type=Path, default=Path(os.environ.get("MODELS_DIR", "models")),
                    help="models directory (default: $MODELS_DIR or ./models)")
    ap.add_argument("--work-dir", type=Path, default=None,
                    help="where the 16 kHz WAV is kept (default: next to --out)")
    ap.add_argument("--source-url", default=None, help="recorded in source.url")
    ap.add_argument("--episode-id", default=None, help="uuid to record; generated if absent")

    g = ap.add_argument_group("asr (PLAN §2)")
    g.add_argument("--fp32", dest="int8", action="store_false", help="use fp32 ONNX graphs")
    g.add_argument("--threads", type=int, default=int(os.environ.get("ASR_NUM_THREADS", 3)))
    g.add_argument("--blank-penalty", type=float,
                   default=float(os.environ.get("ASR_BLANK_PENALTY", 0.25)))
    g.add_argument("--decoding-method",
                   choices=["greedy_search", "modified_beam_search"],
                   default=os.environ.get("ASR_DECODING_METHOD", "modified_beam_search"))
    g.add_argument("--max-active-paths", type=int, default=4)
    g.add_argument("--hotwords", type=Path, default=None,
                   help="hotwords file (needs modified_beam_search)")
    g.add_argument("--hotwords-score", type=float, default=1.5)

    g = ap.add_argument_group("vad (PLAN §3)")
    g.add_argument("--vad-threshold", type=float,
                   default=float(os.environ.get("VAD_THRESHOLD", 0.3)))
    g.add_argument("--vad-pad", type=float, default=0.35)
    g.add_argument("--vad-max-segment", type=float, default=25.0)

    g = ap.add_argument_group("diarization (PLAN §3)")
    g.add_argument("--no-diarize", action="store_true",
                   help="skip diarization; every word gets speaker -1")
    g.add_argument("--diar-threshold", type=float,
                   default=float(os.environ.get("DIAR_THRESHOLD", 0.7)))
    g.add_argument("--diar-num-clusters", type=int, default=0,
                   help="0 = auto (PLAN §5)")

    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # PLAN §3: one worker, ASR num_threads=3 on a 4 vCPU box.
    os.environ.setdefault("OMP_NUM_THREADS", str(args.threads))

    models = args.models
    out = args.out
    if out.exists() and not args.force:
        print(
            f"error: {out} exists. The raw JSON is immutable (PLAN §0.2); "
            "choose another path or pass --force.",
            file=sys.stderr,
        )
        return 1

    hotwords_sha = None
    hotwords_file = None
    if args.hotwords:
        hotwords_file = str(args.hotwords)
        import hashlib

        hotwords_sha = hashlib.sha256(args.hotwords.read_bytes()).hexdigest()

    asr_params = AsrParams(
        model_dir=str(models / "zipformer-30m-rnnt-6000h"),
        int8=args.int8,
        num_threads=args.threads,
        blank_penalty=args.blank_penalty,
        decoding_method=args.decoding_method,
        max_active_paths=args.max_active_paths,
        hotwords_file=hotwords_file,
        hotwords_score=args.hotwords_score,
    )
    vad_params = VadParams(
        model=str(models / "vad" / "silero_vad.onnx"),
        threshold=args.vad_threshold,
        pad_s=args.vad_pad,
        max_segment_s=args.vad_max_segment,
    )
    diar_params = None
    if not args.no_diarize:
        seg = os.environ.get("DIAR_SEGMENTATION_MODEL") or str(
            models / "diarization" / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
        )
        emb = os.environ.get("DIAR_EMBEDDING_MODEL")
        if not emb:
            candidates = sorted((models / "diarization" / "speaker-embedding").glob("*.onnx"))
            if not candidates:
                print(
                    "error: no speaker-embedding model found. Run "
                    "`python scripts/download_models.py --dest models`, or pass "
                    "--no-diarize.",
                    file=sys.stderr,
                )
                return 1
            emb = str(candidates[0])
        diar_params = DiarParams(
            segmentation_model=seg,
            embedding_model=emb,
            threshold=args.diar_threshold,
            num_clusters=args.diar_num_clusters,
            num_threads=args.threads,
        )

    work_dir = args.work_dir or out.parent / "wav"
    try:
        doc = transcribe(
            args.audio,
            work_dir=work_dir,
            asr_params=asr_params,
            vad_params=vad_params,
            diar_params=diar_params,
            source_url=args.source_url,
            episode_id=args.episode_id,
            hotwords_sha256=hotwords_sha,
        )
    except audio_mod.FfmpegMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    write_raw_json(doc, out, force=args.force)
    print(report(doc, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
