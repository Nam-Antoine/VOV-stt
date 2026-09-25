"""Sync the Google repository from the database (Task 7).

    python -m app.google_repo.sync --all          # every Doc, then the Sheet
    python -m app.google_repo.sync --episode ID   # one Doc (slug or UUID), then the Sheet
    python -m app.google_repo.sync --status       # counts only; writes nothing

The worker runs the same code as ``google_sync`` jobs: one is queued when an episode
finishes transcribing, and one (debounced) after an edit is saved. Every entry point
does nothing when ``GOOGLE_REPO_ENABLED`` is false.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Episode, EpisodeGoogleDoc, Job, Transcript
from . import state
from .client import Google, connect
from .docs import ensure_folder, upsert_doc
from .sheet import rebuild_sheet, sheet_url

log = logging.getLogger("google_repo")


def enabled() -> bool:
    return bool(settings.google_repo_enabled)


def sync(session: Session, episodes: list[Episode], *, g: Google | None = None,
         full: bool = False) -> dict[str, int]:
    """Upsert the Docs of ``episodes``, then rebuild the Sheet. Commits per episode."""
    if not enabled():
        return {}
    g = g or connect()
    folder_id = ensure_folder(session, g)
    session.commit()
    counts: dict[str, int] = {}
    for episode in episodes:
        outcome = upsert_doc(session, g, episode, folder_id)
        session.commit()
        counts[outcome] = counts.get(outcome, 0) + 1
    counts["sheet_written"] = int(rebuild_sheet(session, g))
    if full:
        state.put(session, state.LAST_FULL_SYNC, datetime.now(UTC).isoformat())
    session.commit()
    return counts


def all_episodes(session: Session) -> list[Episode]:
    return list(session.scalars(
        select(Episode).order_by(Episode.air_date.asc().nulls_last(), Episode.slug)))


def find_episode(session: Session, ref: str) -> Episode | None:
    try:
        return session.get(Episode, uuid.UUID(ref))
    except ValueError:
        return session.scalar(select(Episode).where(Episode.slug == ref))


def status(session: Session) -> dict[str, int]:
    """synced / pending / errors / orphans. Reads only."""
    transcribed = set(session.scalars(
        select(Transcript.episode_id).where(Transcript.is_current.is_(True))))
    docs = list(session.scalars(select(EpisodeGoogleDoc)))
    synced = {d.episode_id for d in docs
              if d.episode_id and d.doc_id and d.synced_at and not d.last_error}
    return {
        "transcribed": len(transcribed),
        "synced": len(synced & transcribed),
        "pending": len(transcribed - synced),
        "errors": sum(1 for d in docs if d.last_error),
        "orphans": sum(1 for d in docs if d.episode_id is None),
    }


# --- jobs --------------------------------------------------------------------------

def enqueue(session: Session, episode_id: uuid.UUID | None, *,
            delay_min: float = 0.0) -> bool:
    """Queue a ``google_sync`` job unless one for the same target is already waiting.

    ``delay_min`` is the debounce: the job is not claimed before then, so a burst of
    edits becomes one Doc write. Flushes only. Returns whether a job was added.
    """
    if not enabled():
        return False
    pending = select(func.count()).select_from(Job).where(
        Job.kind == "google_sync", Job.status == "queued",
        Job.episode_id.is_(None) if episode_id is None else Job.episode_id == episode_id,
    )
    if session.scalar(pending):
        return False
    params: dict = {"all": episode_id is None}
    if delay_min > 0:
        params["not_before"] = (datetime.now(UTC) + timedelta(minutes=delay_min)).isoformat()
    # One try: a failure is either per-episode (stored in last_error, not raised) or
    # the sign-in, which a retry cannot fix.
    session.add(Job(episode_id=episode_id, kind="google_sync", status="queued",
                    params=params, max_attempts=1))
    session.flush()
    return True


def enqueue_after_edit(session: Session, episode_id: uuid.UUID) -> bool:
    return enqueue(session, episode_id, delay_min=settings.google_edit_debounce_min)


def handle_job(session: Session, job: dict) -> str:
    """Worker handler for ``google_sync``."""
    if not enabled():
        return "google repository disabled; nothing done"
    if job.get("episode_id"):
        episode = session.get(Episode, job["episode_id"])
        episodes = [episode] if episode else []
        full = False
    else:
        episodes, full = all_episodes(session), True
    t0 = time.monotonic()
    counts = sync(session, episodes, full=full)
    return f"{json.dumps(counts, sort_keys=True)} in {time.monotonic() - t0:.1f}s"


# --- CLI ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    from ..db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--episode", metavar="ID_OR_SLUG")
    mode.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    with SessionLocal() as session:
        if args.status:
            for k, v in status(session).items():
                print(f"{k:12} {v}")
            sheet_id = state.get(session, state.SHEET_ID)
            print(f"{'sheet':12} {sheet_url(sheet_id) if sheet_id else '-'}")
            print(f"{'last full':12} {state.get(session, state.LAST_FULL_SYNC) or '-'}")
            return 0
        if not enabled():
            print("GOOGLE_REPO_ENABLED is false; nothing done")
            return 1
        if args.episode:
            episode = find_episode(session, args.episode)
            if episode is None:
                print(f"no episode {args.episode!r}")
                return 1
            episodes, full = [episode], False
        else:
            episodes, full = all_episodes(session), True
        t0 = time.monotonic()
        counts = sync(session, episodes, full=full)
        print(json.dumps(counts, sort_keys=True), f"in {time.monotonic() - t0:.1f}s")
        sheet_id = state.get(session, state.SHEET_ID)
        if sheet_id:
            print(f"Sheet: {sheet_url(sheet_id)}")
        if args.episode:
            row = session.scalar(select(EpisodeGoogleDoc)
                                 .where(EpisodeGoogleDoc.episode_id == episodes[0].id))
            if row and row.doc_id:
                from .docs import doc_url

                print(f"Doc:   {doc_url(row.doc_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
