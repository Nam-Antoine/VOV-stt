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
from .api import auth, episodes, exports, hotwords, jobs, speakers, transcripts, utterances
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

for module in (auth, episodes, jobs, transcripts, utterances, speakers, hotwords, exports):
    app.include_router(module.router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
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
    )


def _worker_heartbeat_s() -> float | None:
    """Seconds since the worker last touched its heartbeat row.

    TODO(T3): the worker writes ``settings['worker_heartbeat']`` each poll; read it here
    and let ``/api/health`` go unhealthy when it is stale.
    """
    return None


@app.get("/api/stats", response_model=Stats, tags=["ops"])
def stats() -> Stats:
    """Episodes by status, hours transcribed/verified, mean confidence (PLAN §9).

    TODO(T3).
    """
    return Stats()


@app.middleware("http")
async def log_slow_requests(request, call_next):
    """Surface slow endpoints — transcript reads carry a few thousand words."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    if elapsed > 1.0:
        log.info("slow: %s %s took %.2fs", request.method, request.url.path, elapsed)
    return response
