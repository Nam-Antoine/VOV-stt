"""Job worker — Postgres as the queue (PLAN §6, §11 T3).

    python -m app.worker

One process, one job at a time, no Redis: on a 6 GB box with one ASR pipeline that is
the whole story (PLAN §3, CLAUDE.md rule 6). Do not scale this service; two workers
would run two episodes concurrently and OOM the box.

Claim query (PLAN §8)::

    UPDATE jobs SET status='running', locked_at=now() WHERE id = (
      SELECT id FROM jobs WHERE status='queued' ORDER BY created_at
      FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *;

T1 status: the loop and the claim query are real; :func:`handle_transcribe` is the T3
piece that writes rows from the raw JSON. The pipeline it will call
(:mod:`app.pipeline.run`) already works standalone.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from .config import settings
from .db import session_scope

log = logging.getLogger("worker")

CLAIM_SQL = text(
    """
    UPDATE jobs
       SET status = 'running',
           locked_at = now(),
           started_at = coalesce(started_at, now()),
           attempts = attempts + 1
     WHERE id = (
        SELECT id FROM jobs
         WHERE status = 'queued'
           -- google_sync edit debounce (app/google_repo/sync.py)
           AND (params->>'not_before' IS NULL
                OR (params->>'not_before')::timestamptz <= now())
         ORDER BY created_at
           FOR UPDATE SKIP LOCKED
         LIMIT 1
     )
    RETURNING id, episode_id, kind, params, attempts, max_attempts;
    """
)

FINISH_SQL = text(
    """
    UPDATE jobs
       SET status = :status, error = :error, log = :log, finished_at = now()
     WHERE id = :id;
    """
)

REQUEUE_SQL = text(
    """
    UPDATE jobs
       SET status = 'queued', locked_at = NULL, error = :error, log = :log
     WHERE id = :id;
    """
)


HEARTBEAT_SQL = text(
    """
    INSERT INTO settings (key, value) VALUES ('worker_heartbeat', :value)
    ON CONFLICT (key) DO UPDATE SET value = excluded.value;
    """
)


REQUEUE_ORPHANS_SQL = text(
    """
    UPDATE jobs
       SET status = 'queued', locked_at = NULL,
           error = coalesce(error, 'requeued: worker restarted mid-job')
     WHERE status = 'running'
    RETURNING id;
    """
)


def requeue_orphans(session) -> int:  # noqa: ANN001
    """Re-queue jobs left 'running' by a worker that died.

    CLAUDE.md rule 6: there is exactly one worker process. So at startup *any* row still
    marked running is by definition orphaned — a deploy, an OOM kill or a crash left it
    there, and nothing will ever finish it. Without this, a restart mid-episode silently
    strands that episode in 'processing' forever.

    Safe to re-run: the transcribe handler writes a new raw JSON per attempt and never
    edits an existing one (PLAN §0.2).
    """
    ids = session.execute(REQUEUE_ORPHANS_SQL).scalars().all()
    if ids:
        session.execute(
            text("UPDATE episodes SET status = 'queued' "
                 "WHERE status = 'processing'")
        )
        log.warning("re-queued %d job(s) orphaned by a previous worker", len(ids))
    return len(ids)


def beat(session) -> None:  # noqa: ANN001
    """Record that the worker is alive, for ``/api/health`` (PLAN §11 T5)."""
    session.execute(HEARTBEAT_SQL, {"value": json.dumps({"at": time.time()})})


#: Seconds between heartbeats while a job runs. The UI calls the worker stalled after
#: 120 s of silence, and one episode takes several minutes.
HEARTBEAT_EVERY_S = 30.0


def _beat_forever() -> None:
    """Keep the heartbeat fresh during a job; ``run_once`` alone only beats between jobs.

    A daemon thread with its own session, so it dies with the process: a crashed or
    OOM-killed worker still goes quiet, which is what the header chip is for.
    """
    while not _stop:
        try:
            with session_scope() as session:
                beat(session)
        except Exception as exc:  # noqa: BLE001 — a DB blip must not kill the thread
            log.debug("heartbeat skipped: %s", exc)
        time.sleep(HEARTBEAT_EVERY_S)


class Stopping(Exception):
    """Raised by the SIGTERM handler so a poll sleep unwinds cleanly."""


_stop = False


def _handle_signal(signum, frame) -> None:  # noqa: ANN001
    global _stop
    log.info("signal %s received; finishing the current job then exiting", signum)
    _stop = True


def claim_job(session) -> dict[str, Any] | None:  # noqa: ANN001
    """Claim one queued job, or return ``None``."""
    row = session.execute(CLAIM_SQL).mappings().first()
    session.commit()
    return dict(row) if row else None


def handle_transcribe(session, job: dict) -> str:  # noqa: ANN001
    """Run the pipeline for one episode and load the results into the DB.

    The raw JSON is written **once**, before any row is inserted: if the DB load fails
    the master record still exists on disk and can be replayed (PLAN §0.2). Existing
    verified utterances from an earlier transcript are neither migrated nor overwritten
    — a new run is a new transcript row, and the human layer stays attached to the run
    it was made against.
    """
    import uuid as _uuid

    from . import loader
    from .models import Episode, Hotword
    from .pipeline import hotwords as hotwords_mod
    from .pipeline import run as run_mod

    episode = session.get(Episode, job["episode_id"])
    if episode is None:
        raise ValueError(f"job {job['id']} has no episode")
    if not episode.audio_path or not Path(episode.audio_path).exists():
        raise FileNotFoundError(
            f"episode {episode.slug}: audio missing at {episode.audio_path!r}"
        )

    params = dict(job.get("params") or {})
    episode.status = "processing"
    session.flush()
    session.commit()

    # --- hotwords: render the active terms to a file the recognizer can load ---
    hotwords_file = None
    hotwords_sha = None
    if params.get("hotwords", True):
        terms = list(session.scalars(
            select(Hotword.term)
            .where(Hotword.active.is_(True))
            .order_by(Hotword.weight.desc(), Hotword.id)
        ))
        bpe = settings.asr_model_dir / "bpe.model"
        if bpe.exists():
            for term in terms:
                bad = hotwords_mod.unencodable(term, bpe)
                if bad:
                    log.warning("hotword %r has no effect: model cannot encode %s "
                                "(its vocabulary is UPPERCASE spoken form)", term, bad)
        rendered = hotwords_mod.write(terms, settings.hotwords_file)
        if rendered.enabled:
            hotwords_file = str(rendered.path)
            hotwords_sha = rendered.sha256
            log.info("hotwords: %d terms (sha %s)", rendered.count, hotwords_sha[:12])

    asr_params = settings.asr_params(hotwords_file=hotwords_file)
    if params.get("blank_penalty") is not None:
        asr_params = replace(asr_params, blank_penalty=float(params["blank_penalty"]))
    if params.get("decoding_method"):
        asr_params = replace(asr_params, decoding_method=str(params["decoding_method"]))

    vad_params = settings.vad_params()
    if params.get("vad_threshold") is not None:
        vad_params = replace(vad_params, threshold=float(params["vad_threshold"]))

    log.info("transcribing %s", episode.slug)
    doc = run_mod.transcribe(
        Path(episode.audio_path), work_dir=settings.audio_dir,
        asr_params=asr_params, vad_params=vad_params,
        source_url=episode.source_url, episode_id=str(episode.id),
        hotwords_sha256=hotwords_sha,
    )
    transcript_id = _uuid.uuid4()
    out_path = loader.raw_json_dest(settings.raw_dir, episode.slug, transcript_id)
    run_mod.write_raw_json(doc, out_path)

    loader.load_transcript(
        session,
        episode=episode,
        doc=doc,
        raw_json_path=out_path,
        transcript_id=transcript_id,
        hotwords_sha256=hotwords_sha,
    )

    readable_note = add_readable_layer(session, transcript_id)

    audio_block = doc.get("audio") or {}
    if audio_block.get("duration_s"):
        episode.duration_s = float(audio_block["duration_s"])
    episode.status = "transcribed"
    session.flush()
    from .google_repo import sync as google_sync

    google_sync.enqueue(session, episode.id)

    timing = doc.get("timing") or {}
    return (
        f"{len(doc.get('words') or [])} words, "
        f"{len(doc.get('utterances') or [])} utterances, "
        f"rtf {timing.get('realtime_factor')}x, "
        f"peak rss {timing.get('peak_rss_mb')} MB{readable_note} -> {out_path}"
    )


def add_readable_layer(session, transcript_id) -> str:  # noqa: ANN001
    """Punctuation + capitals for reading (app/readable.py). ~20 s per 14-min episode.

    A derived layer only: the corpus text was written above and is not touched. If the
    model is missing or fails, the transcript is still complete — the layer is filled
    in later on demand (POST /transcripts/{id}/readable, or a readable export).
    """
    from . import readable as readable_mod
    from .pipeline import punctuate

    if not settings.punct_available():
        log.info("readable: model not installed; skipping")
        return ""
    t0 = time.monotonic()
    # Savepoint: a failure here must roll back only the reading layer, never the
    # transcript that was just loaded in this same transaction.
    savepoint = session.begin_nested()
    try:
        n = readable_mod.refresh(session, transcript_id,
                                 punctuate.get(settings.punct_params()))
        savepoint.commit()
    except Exception:  # noqa: BLE001 — never fail a transcription over the reading copy
        log.exception("readable: failed; transcript kept without it")
        savepoint.rollback()
        return ", readable failed"
    return f", readable {n} utt in {time.monotonic() - t0:.1f}s"


def handle_export(session, job: dict) -> str:  # noqa: ANN001
    """Regenerate every export for one episode into ``/data/exports``.

    Always rebuilt from the raw JSON plus the verified layer — never from a previous
    export, which would let a stale file drift into being the source of truth (§0.2).
    """
    from . import loader
    from .exports import __main__ as exports_main
    from .models import Episode

    episode = session.get(Episode, job["episode_id"])
    if episode is None:
        raise ValueError(f"job {job['id']} has no episode")

    transcript = loader.current_transcript(session, episode.id)
    if transcript is None:
        raise ValueError(f"episode {episode.slug} has no transcript to export")

    doc = json.loads(Path(transcript.raw_json_path).read_text(encoding="utf-8"))
    written = exports_main.render_all(
        doc,
        settings.exports_dir / episode.slug,
        episode.slug,
        overrides=loader.overrides_for(session, transcript.id),
    )
    return f"{len(written)} exports -> {settings.exports_dir / episode.slug}"


def handle_google_sync(session, job: dict) -> str:  # noqa: ANN001
    """Upsert one episode's Google Doc (or all), then rebuild the index Sheet."""
    from .google_repo import sync as google_sync

    return google_sync.handle_job(session, job)


HANDLERS = {
    "transcribe": handle_transcribe,
    "export": handle_export,
    "google_sync": handle_google_sync,
}


def run_once() -> bool:
    """Claim and run at most one job. Returns True if a job was handled."""
    with session_scope() as session:
        beat(session)
        job = claim_job(session)
        if job is None:
            return False

        log.info("job %s (%s) attempt %d/%d",
                 job["id"], job["kind"], job["attempts"], job["max_attempts"])
        handler = HANDLERS.get(job["kind"])
        try:
            if handler is None:
                raise ValueError(f"unknown job kind {job['kind']!r}")
            output = handler(session, job)
            session.execute(
                FINISH_SQL,
                {"id": job["id"], "status": "done", "error": None, "log": output},
            )
            log.info("job %s done", job["id"])
        except Exception as exc:  # noqa: BLE001 — a failed job must not kill the worker
            log.exception("job %s failed", job["id"])
            exhausted = job["attempts"] >= job["max_attempts"]
            sql = FINISH_SQL if exhausted else REQUEUE_SQL
            params = {"id": job["id"], "error": f"{type(exc).__name__}: {exc}",
                      "log": None}
            if exhausted:
                params["status"] = "failed"
            session.execute(sql, params)
    return True


def backoff_s(attempts: int) -> float:
    """Exponential backoff between retries, capped at 5 minutes (PLAN §11 T3)."""
    return min(300.0, 5.0 * (2 ** max(0, attempts - 1)))


def main() -> int:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    settings.ensure_dirs()
    try:
        with session_scope() as session:
            requeue_orphans(session)
    except Exception as exc:  # noqa: BLE001 — schema may not exist yet on first boot
        log.debug("orphan sweep skipped: %s", exc)
    if settings.worker_nice:
        try:
            os.nice(settings.worker_nice)
        except OSError as exc:  # pragma: no cover — container may forbid it
            log.warning("could not renice worker: %s", exc)
    threading.Thread(target=_beat_forever, name="heartbeat", daemon=True).start()
    log.info("worker up; polling every %.1fs", settings.worker_poll_interval_s)

    consecutive_errors = 0
    while not _stop:
        try:
            worked = run_once()
            consecutive_errors = 0
        except ProgrammingError as exc:
            # Almost always "relation \"jobs\" does not exist": the stack came up
            # before `alembic upgrade head`. One line, not a traceback every 2 s.
            consecutive_errors += 1
            if consecutive_errors == 1:
                log.warning(
                    "database schema not ready (%s). Run `make migrate`; retrying.",
                    str(exc.orig).splitlines()[0] if exc.orig else exc,
                )
            worked = False
        except Exception:  # noqa: BLE001 — e.g. the DB went away
            consecutive_errors += 1
            log.exception("worker loop error; backing off")
            worked = False
        if not worked:
            # Back off while something is broken so the log stays readable, but keep
            # the normal idle poll snappy.
            delay = settings.worker_poll_interval_s
            if consecutive_errors:
                delay = min(60.0, backoff_s(consecutive_errors))
            time.sleep(delay)
    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
