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

import logging
import signal
import time
from typing import Any

from sqlalchemy import text
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

    TODO(T3), in this order:

    1. Load the episode; resolve its audio path.
    2. Render active hotwords to ``/data/models/hotwords.txt`` via
       :mod:`app.pipeline.hotwords`, keeping the sha256.
    3. Call :func:`app.pipeline.run.transcribe` with the settings' params.
    4. Write the raw JSON to ``/data/raw/<episode>/<transcript_id>.json`` — **once**,
       never overwriting (PLAN §0.2).
    5. Insert the ``transcripts`` row, flip the previous one's ``is_current`` to false.
    6. Bulk-insert ``words`` and ``utterances`` (``text_asr`` frozen from the JSON,
       ``text_verified`` left NULL).
    7. Upsert ``speakers`` rows for the clusters that appeared.
    8. Set ``episodes.status = 'transcribed'``.

    Existing verified utterances from an earlier transcript are **not** migrated or
    overwritten: a new run is a new transcript row, and the human layer stays attached
    to the run it was made against.
    """
    raise NotImplementedError("T3: transcribe job handler")


def handle_export(session, job: dict) -> str:  # noqa: ANN001
    """Regenerate every export for one episode into ``/data/exports``.

    TODO(T3): call the renderers in :mod:`app.exports`; they are already written and
    tested.
    """
    raise NotImplementedError("T3: export job handler")


HANDLERS = {"transcribe": handle_transcribe, "export": handle_export}


def run_once() -> bool:
    """Claim and run at most one job. Returns True if a job was handled."""
    with session_scope() as session:
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
