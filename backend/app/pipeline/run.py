"""Transcribe one episode end-to-end and write the raw JSON (PLAN §3, §5).

    python -m app.pipeline.run --audio x.mp3 --out x.json

Stages: ffmpeg → Silero VAD → Zipformer ASR per segment → utterance grouping → raw
JSON. ASR runs sequentially on one process (PLAN §3). There is no diarization: the
transcript carries no speaker information.

The JSON this writes is the **immutable master record** (PLAN §0.2). It is written once;
a re-run produces a new file, never an edit of an existing one. ``--out`` refuses to
overwrite unless ``--force`` is given.

Prints a realtime factor and peak RSS at the end. PLAN §11 T1: the run must stay under
2 GB RSS on the 6 GB box.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import resource
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import asr as asr_mod
from . import audio as audio_mod
from . import merge as merge_mod
from .asr import AsrParams
from .vad import VadParams

log = logging.getLogger("pipeline.run")

#: 2: no diarization — no ``diarization`` block, no ``speaker`` on words or utterances.
#: Version-1 files (with speakers) still load; the speaker fields are ignored.
SCHEMA_VERSION = 2


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

    @property
    def total_s(self) -> float:
        return sum(self.stages.values())


def transcribe(
    audio_path: Path,
    *,
    work_dir: Path,
    asr_params: AsrParams,
    vad_params: VadParams,
    source_url: str | None = None,
    episode_id: str | None = None,
    hotwords_sha256: str | None = None,
) -> dict:
    """Run every stage and return the raw JSON document (PLAN §5 schema)."""
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

    utterances = merge_mod.build_utterances(words, breaks=[s for s, _ in segments])
    watch.mark("group")

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id or str(uuid.uuid4()),
        "source": info.as_source_block(source_url),
        "audio": info.as_audio_block(),
        "engine": asr_mod.engine_block(asr_params, hotwords_sha256=hotwords_sha256),
        "vad": {**vad_params.as_json(),
                "segments": [[round(s, 3), round(e, 3)] for s, e in segments]},
        "words": [
            {
                "i": w["i"], "text": w["text"],
                "start": round(float(w["start"]), 3),
                "end": round(float(w["end"]), 3) if w.get("end") is not None else None,
                "conf": w.get("conf"),
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
    lines = [
        "",
        "─" * 66,
        f"  audio            {dur:8.1f} s   ({dur / 60:.1f} min)",
        f"  vad speech       {speech_s:8.1f} s   ({100 * speech_s / dur:.0f}% coverage, "
        f"{len(doc['vad']['segments'])} segments)",
        f"  words            {len(doc['words']):8d}",
        f"  utterances       {len(doc['utterances']):8d}",
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
    work_dir = args.work_dir or out.parent / "wav"
    try:
        doc = transcribe(
            args.audio,
            work_dir=work_dir,
            asr_params=asr_params,
            vad_params=vad_params,
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
