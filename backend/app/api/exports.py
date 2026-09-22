"""Export endpoints (PLAN §9).

    GET /episodes/{id}/export.{json|verified.json|eaf|txt|csv|srt}
    GET /exports/corpus.zip?tier=verified|all

Every response is regenerated from the raw JSON plus the verified layer (PLAN §0.2) —
nothing is cached to disk and then drifted from. The render functions in
:mod:`app.exports` already exist and are covered by ``test_no_normalisation``; what is
missing here is the DB plumbing that loads a transcript and its overrides.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_session
from . import not_implemented

router = APIRouter(tags=["exports"])

#: ``format`` path values → (media type, file extension).
FORMATS = {
    "json": ("application/json; charset=utf-8", "json"),
    "verified.json": ("application/json; charset=utf-8", "verified.json"),
    "eaf": ("application/xml; charset=utf-8", "eaf"),
    "txt": ("text/plain; charset=utf-8", "txt"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "srt": ("application/x-subrip; charset=utf-8", "srt"),
}


@router.get("/episodes/{episode_id}/export.{fmt}")
def export_episode(
    episode_id: uuid.UUID, fmt: str, session: Session = Depends(get_session)
) -> Response:
    """One episode in one format.

    TODO(T3): load the current transcript's raw JSON, overlay ``utterances`` rows and
    ``speakers`` labels, then call the matching renderer in :mod:`app.exports`. Always
    ``charset=utf-8`` (CLAUDE.md rule 3).
    """
    raise not_implemented("episode export")


@router.get("/exports/corpus.zip")
def export_corpus(
    tier: str = Query("verified", pattern="^(verified|all)$"),
    session: Session = Depends(get_session),
) -> Response:
    """The whole corpus as a zip.

    TODO(T3): stream the zip; ``tier=verified`` includes only episodes marked verified,
    ``tier=all`` includes everything with a transcript.
    """
    raise not_implemented("corpus export")
