"""Sync the Google repository from the database (Task 7 + projects).

    python -m app.google_repo.sync --all              # every project: Docs, then Sheet
    python -m app.google_repo.sync --project SLUG      # one project (even with 0 episodes)
    python -m app.google_repo.sync --episode ID        # one Doc (slug or UUID)
    python -m app.google_repo.sync --status             # counts only; writes nothing
    python -m app.google_repo.sync --share              # re-apply GOOGLE_SHARE_EDITORS

The worker runs the same code as ``google_sync`` jobs: one is queued when an episode
finishes transcribing, one (debounced) after an edit is saved, and one when a project is
created or renamed (api/projects.py). Every entry point does nothing when
``GOOGLE_REPO_ENABLED`` is false.
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
from ..models import Episode, EpisodeGoogleDoc, Job, Project, Transcript
from .client import Google, connect
from .docs import ensure_folder, share_editors, upsert_doc
from .sheet import rebuild_sheet, sheet_url

log = logging.getLogger("google_repo")


def enabled() -> bool:
    return bool(settings.google_repo_enabled)


def sync(session: Session, episodes: list[Episode], *, g: Google | None = None,
         full: bool = False, extra_project_ids: tuple[uuid.UUID, ...] = ()) -> dict[str, int]:
    """Upsert the Docs of ``episodes``, grouped by project, then rebuild each project's
    Sheet exactly once. ``extra_project_ids`` are synced (folder + Sheet) even with no
    episodes among ``episodes`` — how a brand-new, still-empty project gets its folder
    and Sheet right away. Commits per episode and per project."""
    if not enabled():
        return {}
    g = g or connect()
    by_project: dict[uuid.UUID, list[Episode]] = {}
    for episode in episodes:
        by_project.setdefault(episode.project_id, []).append(episode)
    for project_id in extra_project_ids:
        by_project.setdefault(project_id, [])

    counts: dict[str, int] = {}
    sheet_written = 0
    for project_id, eps in by_project.items():
        project = session.get(Project, project_id)
        if project is None:  # deleted mid-sync — nothing left to write for it
            continue
        folder_id = ensure_folder(session, g, project)
        session.commit()
        for episode in eps:
            outcome = upsert_doc(session, g, episode, folder_id)
            session.commit()
            counts[outcome] = counts.get(outcome, 0) + 1
        if rebuild_sheet(session, g, project):
            sheet_written += 1
        if full:
            project.google_last_full_sync = datetime.now(UTC).isoformat()
        session.commit()
    counts["sheet_written"] = sheet_written
    return counts


def all_episodes(session: Session, project_id: uuid.UUID | None = None) -> list[Episode]:
    stmt = select(Episode).order_by(Episode.air_date.asc().nulls_last(), Episode.slug)
    if project_id is not None:
        stmt = stmt.where(Episode.project_id == project_id)
    return list(session.scalars(stmt))


def find_episode(session: Session, ref: str) -> Episode | None:
    try:
        return session.get(Episode, uuid.UUID(ref))
    except ValueError:
        return session.scalar(select(Episode).where(Episode.slug == ref))


def find_project(session: Session, ref: str) -> Project | None:
    try:
        return session.get(Project, uuid.UUID(ref))
    except ValueError:
        return session.scalar(select(Project).where(Project.slug == ref))


def all_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.created_at)))


def share_all_folders(session: Session, g: Google | None = None) -> int:
    """Re-apply ``GOOGLE_SHARE_EDITORS`` to every project's existing folder.

    For a folder made before an address was added to the list, or shared by hand and
    then dropped — never touches anything else in Drive.
    """
    if not enabled():
        return 0
    g = g or connect()
    n = 0
    for project in all_projects(session):
        if project.google_folder_id:
            share_editors(g, project.google_folder_id)
            n += 1
    return n


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
    """Queue a ``google_sync`` job for one episode (or, with ``episode_id=None``,
    every project) unless one for the same target is already waiting.

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


def enqueue_project(session: Session, project_id: uuid.UUID) -> bool:
    """Queue a sync of one project (its folder/Sheet and every episode's Doc).

    Used when a project is created or renamed, so its Sheet appears without waiting for
    an episode to be uploaded, and when an episode moves out of a project, so the row
    leaves its old Sheet right away.
    """
    if not enabled():
        return False
    pending = select(func.count()).select_from(Job).where(
        Job.kind == "google_sync", Job.status == "queued", Job.episode_id.is_(None),
        Job.params["project_id"].astext == str(project_id),
    )
    if session.scalar(pending):
        return False
    session.add(Job(episode_id=None, kind="google_sync", status="queued",
                    params={"all": False, "project_id": str(project_id)}, max_attempts=1))
    session.flush()
    return True


def enqueue_after_edit(session: Session, episode_id: uuid.UUID) -> bool:
    return enqueue(session, episode_id, delay_min=settings.google_edit_debounce_min)


def handle_job(session: Session, job: dict) -> str:
    """Worker handler for ``google_sync``."""
    if not enabled():
        return "google repository disabled; nothing done"
    params = job.get("params") or {}
    if job.get("episode_id"):
        episode = session.get(Episode, job["episode_id"])
        episodes = [episode] if episode else []
        extra: tuple[uuid.UUID, ...] = ()
        full = False
    elif params.get("project_id"):
        project_id = uuid.UUID(params["project_id"])
        episodes = all_episodes(session, project_id=project_id)
        extra = (project_id,)
        full = True
    else:
        episodes, extra, full = all_episodes(session), (), True
    t0 = time.monotonic()
    counts = sync(session, episodes, full=full, extra_project_ids=extra)
    return f"{json.dumps(counts, sort_keys=True)} in {time.monotonic() - t0:.1f}s"


# --- CLI ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    from ..db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--project", metavar="SLUG_OR_ID")
    mode.add_argument("--episode", metavar="ID_OR_SLUG")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--share", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    with SessionLocal() as session:
        if args.status:
            for k, v in status(session).items():
                print(f"{k:12} {v}")
            for project in all_projects(session):
                sheet = sheet_url(project.google_sheet_id) if project.google_sheet_id else "-"
                print(f"{project.slug:20} {sheet}  (last full: "
                     f"{project.google_last_full_sync or '-'})")
            return 0
        if not enabled():
            print("GOOGLE_REPO_ENABLED is false; nothing done")
            return 1
        if args.share:
            n = share_all_folders(session)
            emails = ", ".join(settings.google_share_editors) or "(none configured)"
            print(f"shared {n} folder(s) with: {emails}")
            return 0
        if args.episode:
            episode = find_episode(session, args.episode)
            if episode is None:
                print(f"no episode {args.episode!r}")
                return 1
            episodes, extra, full = [episode], (), False
        elif args.project:
            project = find_project(session, args.project)
            if project is None:
                print(f"no project {args.project!r}")
                return 1
            episodes = all_episodes(session, project_id=project.id)
            episodes, extra, full = episodes, (project.id,), True
        else:
            episodes, extra, full = all_episodes(session), (), True
        t0 = time.monotonic()
        counts = sync(session, episodes, full=full, extra_project_ids=extra)
        print(json.dumps(counts, sort_keys=True), f"in {time.monotonic() - t0:.1f}s")
        for project in all_projects(session):
            if project.google_sheet_id:
                print(f"Sheet ({project.slug}): {sheet_url(project.google_sheet_id)}")
        if args.episode:
            row = session.scalar(select(EpisodeGoogleDoc)
                                 .where(EpisodeGoogleDoc.episode_id == episodes[0].id))
            if row and row.doc_id:
                from .docs import doc_url

                print(f"Doc:   {doc_url(row.doc_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
