"""FastAPI application (PLAN §6, §9).

Everything is mounted under ``/api``; Caddy serves the static Vite build for every other
path (PLAN §6), so there is no SPA fallback route here.

T1 status: the app boots, ``/api/health`` is real, ``/api/docs`` shows the full §9
contract, and the handlers raise 501 until T3.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import __version__
from .api import (
    auth,
    episodes,
    exports,
    hotwords,
    jobs,
    speakers,
    transcripts,
    users,
    utterances,
)
from .config import settings
from .db import engine
from .schemas import Health, Stats

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("app")

app = FastAPI(
    title="vn-stt-corpus",
    version=__version__,
    description=(
        "VOV2 *Đàn bà 30+* verbatim corpus. Output is a linguistic corpus, not a "
        "readable transcript: fillers, repetitions and false starts are the data "
        "(PLAN §0.1)."
    ),
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

# The Vite dev server runs on a different origin; in production Caddy serves both from
# one origin and this middleware is a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, episodes, jobs, transcripts, utterances, speakers, hotwords, exports,
               users):
    app.include_router(module.router, prefix="/api")


#: Secret keys that ship in the repo (config default, .env.example).
_PLACEHOLDER_KEYS = ("", "dev-only-change-me", "generate-with-openssl-rand-hex-32")


@app.on_event("startup")
def on_startup() -> None:
    if settings.auth_enabled and settings.secret_key in _PLACEHOLDER_KEYS:
        # Anyone who knows the default key could sign a session cookie for any user.
        raise RuntimeError("AUTH_ENABLED=true needs a real SECRET_KEY in .env")
    settings.ensure_dirs()
    missing = [name for name, ok in settings.models_present().items() if not ok]
    if missing:
        log.warning(
            "models missing: %s — run `make models` before enqueuing work",
            ", ".join(missing),
        )


@app.get("/api/health", response_model=Health, tags=["ops"])
def health() -> Health:
    """DB reachable + models present + worker heartbeat (PLAN §11 T5)."""
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001 — health must report, not raise
        log.warning("health: db unreachable: %s", exc)
        db_ok = False

    models = settings.models_present()
    return Health(
        ok=db_ok and all(models.values()),
        db=db_ok,
        models=models,
        worker_heartbeat_s=_worker_heartbeat_s(),
        version=__version__,
        readable_available=settings.punct_available(),
    )


def _worker_heartbeat_s() -> float | None:
    """Seconds since the worker last touched its heartbeat row.

    ``None`` means the worker has never checked in. The caller decides what to do with
    a stale value — health reports it rather than guessing a threshold here.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("select value from settings where key = 'worker_heartbeat'")
            ).scalar()
    except Exception:  # noqa: BLE001 — health must report, not raise
        return None
    if not row:
        return None
    at = row.get("at") if isinstance(row, dict) else None
    return None if at is None else max(0.0, time.time() - float(at))


@app.get("/api/stats", response_model=Stats, tags=["ops"])
def stats() -> Stats:
    """Episodes by status, hours transcribed/verified, mean confidence (PLAN §9)."""
    from sqlalchemy import func, select

    from .db import SessionLocal
    from .models import Episode, Transcript, Utterance, Word

    with SessionLocal() as session:
        by_status = {
            str(status): int(n)
            for status, n in session.execute(
                select(Episode.status, func.count()).group_by(Episode.status)
            ).all()
        }

        # Hours are measured on episodes that actually have a current transcript, not on
        # everything ingested — otherwise a queued backlog reads as finished work.
        transcribed_s = session.scalar(
            select(func.coalesce(func.sum(Episode.duration_s), 0))
            .where(Episode.id.in_(
                select(Transcript.episode_id).where(Transcript.is_current.is_(True))
            ))
        ) or 0

        verified_s = session.scalar(
            select(func.coalesce(
                func.sum(Utterance.end_s - Utterance.start_s), 0
            )).where(Utterance.text_verified.is_not(None))
        ) or 0

        mean_conf = session.scalar(select(func.avg(Word.conf)))

    return Stats(
        episodes_by_status=by_status,
        hours_transcribed=round(float(transcribed_s) / 3600.0, 2),
        hours_verified=round(float(verified_s) / 3600.0, 2),
        mean_conf=None if mean_conf is None else round(float(mean_conf), 4),
    )


@app.middleware("http")
async def log_slow_requests(request, call_next):
    """Surface slow endpoints — transcript reads carry a few thousand words."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    if elapsed > 1.0:
        log.info("slow: %s %s took %.2fs", request.method, request.url.path, elapsed)
    return response
