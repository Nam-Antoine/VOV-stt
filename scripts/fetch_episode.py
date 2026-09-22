#!/usr/bin/env python3
"""Fetch one episode's audio from a URL into ``/data/audio`` (PLAN §7, §9).

Tries a direct media URL first, then falls back to ``yt-dlp`` for page URLs. vovlive.vn
episode pages embed an mp3, which ``yt-dlp`` generally finds.

**Manual ingest only.** There is no crawler in v1: the ongoing-service path is someone
pasting a new episode URL. A scheduled poller is a v2 item and needs a robots/ToS check
first (PLAN §9).

Records the source URL and sha256 so the transcript can be traced back to the exact
bytes that produced it.

Usage
-----
    python scripts/fetch_episode.py --url https://vovlive.vn/... --dest /data/audio
    python scripts/fetch_episode.py --url ... --dest /data/audio --slug ep042
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac"}


def slugify(value: str) -> str:
    """ASCII slug for filenames only.

    This touches **filenames, never transcript text** — the stripping here would be a
    bug anywhere in the pipeline (CLAUDE.md rule 1), which is why it lives in a script
    and not in ``app/``.
    """
    ascii_ = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_).strip("-").lower()
    return slug or "episode"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def looks_like_media(url: str) -> bool:
    return Path(urlparse(url).path).suffix.lower() in AUDIO_SUFFIXES


def fetch_direct(url: str, dest_dir: Path, slug: str) -> Path:
    """Download a direct media URL with ffmpeg (already a dependency)."""
    suffix = Path(urlparse(url).path).suffix.lower() or ".mp3"
    out = dest_dir / f"{slug}{suffix}"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-i", url, "-c", "copy", str(out)],
        check=True,
    )
    return out


def fetch_with_ytdlp(url: str, dest_dir: Path, slug: str) -> Path:
    """Fall back to yt-dlp for page URLs (vovlive.vn, vtcnews.vn, YouTube …)."""
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError(
            "yt-dlp not found. Install it (pip install yt-dlp) or pass a direct media URL."
        )
    template = str(dest_dir / f"{slug}.%(ext)s")
    subprocess.run(
        [ytdlp, "-f", "bestaudio/best", "--no-playlist", "-o", template, url],
        check=True,
    )
    found = sorted(dest_dir.glob(f"{slug}.*"))
    media = [p for p in found if p.suffix.lower() in AUDIO_SUFFIXES]
    if not media:
        raise RuntimeError(f"yt-dlp produced no audio file for {url}")
    return media[0]


def fetch(url: str, dest_dir: Path, slug: str | None = None) -> dict:
    """Download and return a record for the ``episodes`` row."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    slug = slug or slugify(Path(urlparse(url).path).stem or urlparse(url).netloc)

    if looks_like_media(url):
        path = fetch_direct(url, dest_dir, slug)
    else:
        path = fetch_with_ytdlp(url, dest_dir, slug)

    return {
        "slug": slug,
        "source_url": url,
        "audio_path": str(path),
        "audio_sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--dest", type=Path, default=Path("/data/audio"))
    ap.add_argument("--slug", default=None, help="filename stem (default: from the URL)")
    args = ap.parse_args(argv)

    try:
        record = fetch(args.url, args.dest, args.slug)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
