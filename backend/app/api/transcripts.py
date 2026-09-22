"""Transcript reads: the editor payload, the raw JSON, and audio streaming (PLAN §9)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import TranscriptOut
from . import not_implemented

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


@router.get("/{transcript_id}", response_model=TranscriptOut)
def get_transcript(
    transcript_id: uuid.UUID, session: Session = Depends(get_session)
) -> TranscriptOut:
    """Words + utterances + speakers — what the editor loads in one request.

    TODO(T3): a 15-minute episode is a few thousand words; send them in one payload
    rather than paginating, so click-to-play has no gaps.
    """
    raise not_implemented("transcript read")


@router.get("/{transcript_id}/raw")
def get_raw_json(
    transcript_id: uuid.UUID, session: Session = Depends(get_session)
) -> FileResponse:
    """The immutable raw JSON file, served straight off disk (PLAN §0.2).

    TODO(T3): ``media_type="application/json; charset=utf-8"``.
    """
    raise not_implemented("raw JSON download")


@router.get("/{transcript_id}/audio")
def stream_audio(
    transcript_id: uuid.UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Range-request streaming of the episode's 16 kHz WAV.

    TODO(T3): honour ``Range`` with 206 responses — wavesurfer and click-to-play both
    depend on seeking without downloading the whole file.
    """
    raise not_implemented("audio streaming")
