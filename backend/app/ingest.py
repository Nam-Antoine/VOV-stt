"""Turn an uploaded or fetched audio file into an ``episodes`` row (PLAN §9).

Ingest is deliberately dumb: copy the bytes in, hash them, measure the duration, record
where they came from. Nothing here decodes or transcribes — that is the worker's job, so
an upload returns immediately instead of holding an HTTP connection open for minutes.

The sha256 is of the file **as it arrived**. It is what makes a re-upload of the same
episode detectable, and what ties a transcript back to exact bytes (PLAN §5 ``source``).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Episode
from .slugs import slugify, unique_slug

#: Suffixes we accept. ffmpeg handles far more, but an unexpected upload is much more
#: likely to be a mistake than an exotic container.
AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac", ".mp4", ".webm"}

CHUNK = 1 << 20


def store_stream(fileobj, dest: Path) -> str:
    """Stream ``fileobj`` to ``dest``, returning the sha256.

    Streamed in 1 MiB chunks: a 15-minute episode is tens of MB and the box has 6 GB
    shared with Postgres and the worker, so the whole upload is never held in memory.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    digest = hashlib.sha256()
    try:
        with tmp.open("wb") as out:
            while True:
                chunk = fileobj.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        # A half-written upload (disk full, client gone) would otherwise sit in
        # AUDIO_DIR taking space nobody can see.
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)
    return digest.hexdigest()


def probe_duration_s(path: Path) -> float | None:
    """Duration via ffprobe; ``None`` when the file is not decodable.

    A failure here is not fatal at ingest time — the pipeline will decode the file
    properly later and record the authoritative duration measured on the 16 kHz WAV
    (PLAN §13). This is only for the episode list.
    """
    from .pipeline import audio as audio_mod

    try:
        return audio_mod.probe_duration_s(path)
    except Exception:  # noqa: BLE001 — ffprobe failures must not block ingest
        return None


def find_by_sha256(session: Session, sha256: str) -> Episode | None:
    return session.scalar(select(Episode).where(Episode.audio_sha256 == sha256))


def create_episode(
    session: Session,
    *,
    filename: str,
    fileobj,
    title: str | None = None,
    source_url: str | None = None,
    air_date: date | None = None,
    project_id: uuid.UUID | None = None,
) -> tuple[Episode, bool]:
    """Store the audio and create the episode row, filed under ``project_id``.

    Returns ``(episode, created)``. When the same bytes are already ingested the
    existing episode is returned with ``created=False`` rather than a duplicate row —
    re-uploading the same file is a normal operator mistake, not an error. That existing
    episode may belong to a different project than ``project_id``: the caller decides
    whether that is worth telling the operator (it already does — see the Episodes page
    "repeats" banner).
    """
    stem = Path(filename).stem or "episode"
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise ValueError(
            f"định dạng âm thanh không hỗ trợ {suffix!r}; chỉ nhận: "
            + ", ".join(sorted(AUDIO_SUFFIXES))
        )

    settings.ensure_dirs()
    staged = settings.audio_dir / f".incoming-{slugify(stem, fallback='episode')}{suffix}"
    sha256 = store_stream(fileobj, staged)

    existing = find_by_sha256(session, sha256)
    if existing is not None:
        staged.unlink(missing_ok=True)
        return existing, False

    slug = unique_slug(session, Episode.slug, slugify(stem, fallback="episode"))
    final = settings.audio_dir / f"{slug}{suffix}"
    staged.replace(final)

    if project_id is None:
        from .projects import default_project

        project_id = default_project(session).id

    episode = Episode(
        slug=slug,
        project_id=project_id,
        title=title or stem,
        source_url=source_url,
        air_date=air_date,
        audio_path=str(final),
        audio_sha256=sha256,
        duration_s=probe_duration_s(final),
        status="ingested",
    )
    session.add(episode)
    session.flush()
    return episode, True
