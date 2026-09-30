"""Delete an episode's local audio once its transcript is safely in Google Drive.

    python -m app.purge_audio --dry-run      # what would go, and how much space it frees
    python -m app.purge_audio                # delete (checks each Doc in Drive first)

The client's deliverable is text: the index Sheet with one Google Doc per episode. Audio
is only an input, and it is the bulk of the disk (~120 MB per hour of speech with the
16 kHz FLAC). Once an episode is transcribed and its Doc holds the current text, the
original upload, the 16 kHz decode and the player cache can go.

What stays: the episode row (``audio_sha256`` still identifies the exact bytes), the
transcript and every edit in the database, the raw engine JSON (PLAN §0.2), the Doc and
the Sheet. What is lost: playback in the app and re-transcription — both need the audio
again (the harvester manifests keep each episode's source URL).

An episode is purged only when all of these hold:

* it has a current transcript and no transcribe/export/google_sync job waiting on it;
* its Doc exists and was last written with exactly the text the app renders now
  (the same digest :func:`app.google_repo.docs.upsert_doc` compares), with no error;
* with ``verify_drive``, Drive confirms the Doc is there and not trashed.

``PURGE_AUDIO_AFTER_SYNC=true`` makes the worker do this for each episode right after
its Google sync, so harvest → transcribe → Doc → purge runs as a rolling pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import loader, player
from .config import settings
from .models import Episode, EpisodeGoogleDoc, Job
from .pipeline import audio as audio_mod

log = logging.getLogger("purge_audio")


@dataclass
class Outcome:
    purged: bool
    reason: str
    freed_bytes: int = 0


def audio_files(episode: Episode) -> list[Path]:
    """Every local file derived from this episode's audio that still exists."""
    if not episode.audio_path:
        return []
    original = Path(episode.audio_path)
    stem = original.name.removesuffix(original.suffix)
    files = [original] + [original.with_name(stem + suffix)
                          for suffix in (audio_mod.DERIVED_SUFFIX, audio_mod.LEGACY_SUFFIX)]
    # Player cache keys start with the decode's stem, "<stem>.16k" (player._key).
    files += player.cache_dir().glob(f"{stem}.16k-*")
    return [f for f in files if f.exists()]


def _doc_is_current(session: Session, episode: Episode) -> str | None:
    """``None`` when the Doc holds the current text, else why not."""
    from .exports.plain import render_plain

    transcript = loader.current_transcript(session, episode.id)
    if transcript is None:
        return "no transcript"
    row = session.scalar(select(EpisodeGoogleDoc)
                         .where(EpisodeGoogleDoc.episode_id == episode.id))
    if row is None or not row.doc_id or row.synced_at is None:
        return "no Google Doc yet"
    if row.last_error:
        return f"last Doc sync failed: {row.last_error}"
    text, _ = render_plain(session, transcript.id, settings.google_doc_layer, labels=False)
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != row.text_sha256:
        return "Doc is behind the current text (sync pending)"
    return None


def _doc_in_drive(g, doc_id: str) -> str | None:  # noqa: ANN001 — google_repo.client.Google
    from .google_repo.client import call, short_error

    try:
        meta = call(g, g.drive.files().get(fileId=doc_id, fields="id,trashed"))
    except Exception as exc:  # noqa: BLE001 — any doubt means keep the audio
        return f"Doc not confirmed in Drive: {short_error(exc)}"
    return "Doc is in the Drive trash" if meta.get("trashed") else None


def purge_episode(session: Session, episode: Episode, *, dry_run: bool = False,
                  g=None, ignore_job_id=None) -> Outcome:  # noqa: ANN001
    """Delete ``episode``'s local audio if it is safe to (see module docstring).

    ``g`` (a connected :class:`~app.google_repo.client.Google`) turns on the Drive check.
    ``ignore_job_id`` is the calling job itself, still ``running`` while it asks.
    """
    if not episode.audio_path:
        return Outcome(False, "audio already removed")
    pending = select(Job.id).where(Job.episode_id == episode.id,
                                   Job.status.in_(("queued", "running")))
    if ignore_job_id is not None:
        pending = pending.where(Job.id != ignore_job_id)
    if session.scalar(pending.limit(1)) is not None:
        return Outcome(False, "a job is still waiting on this episode")
    reason = _doc_is_current(session, episode)
    if reason is None and g is not None:
        doc_id = session.scalar(select(EpisodeGoogleDoc.doc_id)
                                .where(EpisodeGoogleDoc.episode_id == episode.id))
        reason = _doc_in_drive(g, doc_id)
    if reason is not None:
        return Outcome(False, reason)

    files = audio_files(episode)
    size = sum(f.stat().st_size for f in files)
    if dry_run:
        return Outcome(True, "would purge", size)
    for f in files:
        f.unlink(missing_ok=True)
    episode.audio_path = None
    session.flush()
    log.info("purged audio of %s (%.1f MB)", episode.slug, size / 1e6)
    return Outcome(True, "purged", size)


def purge_after_sync(session: Session, job: dict) -> str | None:
    """Worker hook after an episode's ``google_sync`` job: purge it if that made it safe."""
    if not settings.purge_audio_after_sync or not job.get("episode_id"):
        return None
    episode = session.get(Episode, job["episode_id"])
    if episode is None:
        return None
    outcome = purge_episode(session, episode, ignore_job_id=job["id"])
    session.commit()
    return outcome.reason


def main(argv: list[str] | None = None) -> int:
    from .db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only; delete nothing")
    ap.add_argument("--no-drive-check", action="store_true",
                    help="skip confirming each Doc in Drive (offline use)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    g = None
    if not a.no_drive_check:
        from .google_repo.client import connect
        g = connect()

    kept: dict[str, int] = {}
    purged = freed = 0
    with SessionLocal() as session:
        for episode in session.scalars(select(Episode).where(Episode.audio_path.is_not(None))
                                       .order_by(Episode.slug)).all():
            outcome = purge_episode(session, episode, dry_run=a.dry_run, g=g)
            if outcome.purged:
                purged += 1
                freed += outcome.freed_bytes
            else:
                kept[outcome.reason] = kept.get(outcome.reason, 0) + 1
            if a.dry_run:
                session.rollback()
            else:
                session.commit()
    verb = "would purge" if a.dry_run else "purged"
    print(f"{verb} {purged} episodes, {freed / 1e9:.2f} GB")
    for reason, n in sorted(kept.items(), key=lambda kv: -kv[1]):
        print(f"  kept {n}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
