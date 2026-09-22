"""Episode ingest and listing (PLAN §9)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import (
    EpisodeDetail,
    EpisodeFromUrl,
    EpisodeOut,
    JobOut,
    SpeakerLabel,
    TranscribeRequest,
)
from . import not_implemented

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.get("", response_model=list[EpisodeOut])
def list_episodes(
    status: str | None = Query(None, description="filter by episode status"),
    q: str | None = Query(None, description="substring match on title/slug"),
    session: Session = Depends(get_session),
) -> list[EpisodeOut]:
    """TODO(T3): select episodes, optional status filter and title/slug search."""
    raise not_implemented("episode listing")


@router.post("/upload", response_model=EpisodeOut)
def upload_episode(
    file: UploadFile, session: Session = Depends(get_session)
) -> EpisodeOut:
    """TODO(T3): stream to ``AUDIO_DIR``, sha256 it, create the episode, enqueue ingest."""
    raise not_implemented("episode upload")


@router.post("/from-url", response_model=EpisodeOut)
def episode_from_url(
    body: EpisodeFromUrl, session: Session = Depends(get_session)
) -> EpisodeOut:
    """TODO(T3): hand the URL to ``scripts/fetch_episode.py`` logic, then ingest.

    Manual URL ingest only — no crawler in v1 (PLAN §9).
    """
    raise not_implemented("URL ingest")


@router.get("/{episode_id}", response_model=EpisodeDetail)
def get_episode(
    episode_id: uuid.UUID, session: Session = Depends(get_session)
) -> EpisodeDetail:
    """TODO(T3): episode + current transcript summary + speakers."""
    raise not_implemented("episode detail")


@router.post("/{episode_id}/transcribe", response_model=JobOut)
def enqueue_transcribe(
    episode_id: uuid.UUID,
    body: TranscribeRequest | None = None,
    session: Session = Depends(get_session),
) -> JobOut:
    """TODO(T3): insert a queued ``transcribe`` job with the params override."""
    raise not_implemented("transcribe enqueue")


@router.delete("/{episode_id}")
def delete_episode(
    episode_id: uuid.UUID, session: Session = Depends(get_session)
) -> dict:
    """Delete an episode — only if it has no verified utterances.

    TODO(T3): the raw JSON under ``/data/raw`` is **kept** on disk regardless
    (PLAN §0.2, §9): deleting a DB row must never delete the master record.
    """
    raise not_implemented("episode delete")


@router.put("/{episode_id}/speakers/{cluster}", response_model=SpeakerLabel)
def set_speaker_label(
    episode_id: uuid.UUID,
    cluster: int,
    body: SpeakerLabel,
    session: Session = Depends(get_session),
) -> SpeakerLabel:
    """Rename one cluster for this episode (PLAN §9, §0.3 — free text, not identity)."""
    raise not_implemented("speaker labelling")
