#!/usr/bin/env python3
"""Enqueue transcribe jobs for every audio file without a current transcript (PLAN §11 T5).

The 129-episode backlog is ~32 h of audio: roughly 1 h of ASR plus ~4 h of diarization
on the 4 vCPU box. Run it overnight, then check that no job ended ``failed`` before
declaring the backlog done.

    python scripts/backfill.py --dry-run
    python scripts/backfill.py

TODO(T3): the DB half of this needs the models and the worker's job handler to exist.
The filesystem scan below is real and is already useful for seeing what is waiting.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac"}


def scan_audio(audio_dir: Path) -> list[Path]:
    """Every audio file in ``audio_dir``, sorted, ignoring the derived 16 kHz WAVs."""
    return sorted(
        p for p in audio_dir.rglob("*")
        if p.is_file()
        and p.suffix.lower() in AUDIO_SUFFIXES
        and not p.name.endswith(".16k.wav")
    )


def enqueue(paths: list[Path], *, dry_run: bool) -> int:
    """Create one queued ``transcribe`` job per episode that has no current transcript.

    TODO(T3): for each path — look up or create the ``episodes`` row by sha256, skip it
    when a ``transcripts`` row with ``is_current`` already exists, otherwise insert a
    queued job. One worker drains them sequentially (CLAUDE.md rule 6), so there is no
    rate limiting to do here.
    """
    if dry_run:
        for p in paths:
            print(f"would enqueue: {p}")
        return 0
    raise NotImplementedError("T3: needs the episodes/jobs tables and the job handler")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio-dir", type=Path, default=Path("/data/audio"))
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be enqueued and exit")
    args = ap.parse_args(argv)

    if not args.audio_dir.exists():
        print(f"error: {args.audio_dir} does not exist", file=sys.stderr)
        return 1

    paths = scan_audio(args.audio_dir)
    print(f"{len(paths)} audio files in {args.audio_dir}")
    if not paths:
        return 0
    return enqueue(paths, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
