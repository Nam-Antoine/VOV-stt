"""Episode ingest and listing (PLAN §9)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import ingest, loader
from ..config import settings
from ..db import get_session
from ..models import Episode, Job, Speaker, Transcript, Utterance, Word
from ..schemas import (
    EpisodeDetail,
    EpisodeFromUrl,
    EpisodeListItem,
    EpisodeOut,
    JobOut,
    SpeakerLabel,
    SpeakerOut,
    TranscribeRequest,
)
from .deps import require_admin, require_editor

router = APIRouter(prefix="/episodes", tags=["episodes"])


def _counts(session: Session, episode_ids: list[uuid.UUID]) -> dict:
    """``{episode_id: (transcript_id, n_utterances, n_verified, speakers_pending)}``.

    Done as a single grouped query rather than per row: the Episodes page lists the
    whole backlog and N+1 counting over 129 episodes is a visible stall.
    """
    if not episode_ids:
        return {}
    rows = session.execute(
        select(
            Transcript.episode_id,
            Transcript.id,
            Transcript.speakers_pending,
            func.count(Utterance.id),
            func.count(Utterance.text_verified),
        )
        .select_from(Transcript)
        .outerjoin(Utterance, Utterance.transcript_id == Transcript.id)
        .where(Transcript.episode_id.in_(episode_ids), Transcript.is_current.is_(True))
        .group_by(Transcript.episode_id, Transcript.id, Transcript.speakers_pending)
    ).all()
    return {r[0]: (r[1], int(r[3]), int(r[4]), bool(r[2])) for r in rows}


@router.get("", response_model=list[EpisodeListItem])
def list_episodes(
    status: str | None = Query(None, description="filter by episode status"),
    q: str | None = Query(None, description="substring match on title/slug"),
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> list[EpisodeListItem]:
    stmt = select(Episode).order_by(Episode.created_at.desc())
    if status:
        stmt = stmt.where(Episode.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Episode.title.ilike(like), Episode.slug.ilike(like)))
    episodes = list(session.scalars(stmt))
    counts = _counts(session, [e.id for e in episodes])
    out = []
    for e in episodes:
        tid, total, verified, pending = counts.get(e.id, (None, 0, 0, False))
        out.append(
            EpisodeListItem.model_validate(e).model_copy(
                update={"current_transcript_id": tid,
                        "n_utterances": total, "n_verified": verified,
                        "speakers_pending": pending}
            )
        )
    return out


@router.post("/upload", response_model=EpisodeOut)
def upload_episode(
    file: UploadFile,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> EpisodeOut:
    """Stream to ``AUDIO_DIR``, sha256 it, create the episode.

    Transcription is **not** started here: it is a queued job, so the upload returns as
    soon as the bytes are on disk instead of holding the connection for minutes.
    """
    try:
        episode, created = ingest.create_episode(
            session, filename=file.filename or "episode.mp3", fileobj=file.file
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    session.commit()
    # `created` is False when these exact bytes were already ingested: the existing
    # episode is handed back rather than a second row pointing at identical audio.
    # Callers that auto-queue transcription must therefore check `status` before
    # enqueueing — the episode they get back may already be transcribed.
    del created
    return EpisodeOut.model_validate(episode)


@router.post("/from-url", response_model=EpisodeOut)
def episode_from_url(
    body: EpisodeFromUrl,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> EpisodeOut:
    """Fetch a direct media URL into ``AUDIO_DIR`` and create the episode.

    Manual URL ingest only — no crawler in v1 (PLAN §9). Page URLs that need yt-dlp are
    handled by ``scripts/fetch_episode.py`` on the host; this endpoint takes the direct
    media URL that script resolves to.
    """
    import urllib.request
    from urllib.parse import unquote, urlparse

    name = Path(unquote(urlparse(body.url).path)).name or "episode.mp3"
    try:
        with urllib.request.urlopen(body.url, timeout=120) as response:  # noqa: S310
            episode, _ = ingest.create_episode(
                session,
                filename=name,
                fileobj=response,
                title=body.title,
                source_url=body.url,
                air_date=body.air_date,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001 — network/URL problems are the user's to see
        raise HTTPException(status_code=400, detail=f"không tải được từ URL: {exc}") from None
    session.commit()
    return EpisodeOut.model_validate(episode)


@router.get("/{episode_id}", response_model=EpisodeDetail)
def get_episode(
    episode_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> EpisodeDetail:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tập")

    transcript = loader.current_transcript(session, episode.id)
    total = verified = n_words = 0
    if transcript is not None:
        total, verified = loader.utterance_counts(session, transcript.id)
        n_words = int(session.scalar(
            select(func.count()).select_from(Word)
            .where(Word.transcript_id == transcript.id)
        ) or 0)

    speakers = [
        SpeakerOut(cluster=int(c), label=label)
        for c, label in session.execute(
            select(Speaker.cluster, Speaker.label)
            .where(Speaker.episode_id == episode.id)
            .order_by(Speaker.cluster)
        ).all()
    ]
    return EpisodeDetail.model_validate(episode).model_copy(
        update={
            "current_transcript_id": transcript.id if transcript else None,
            "n_utterances": total,
            "n_verified": verified,
            "n_words": n_words,
            "speakers": speakers,
            "speakers_pending": bool(transcript and transcript.speakers_pending),
        }
    )


@router.post("/{episode_id}/transcribe", response_model=JobOut)
def enqueue_transcribe(
    episode_id: uuid.UUID,
    body: TranscribeRequest | None = None,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> JobOut:
    """Queue a transcribe job. One worker drains the queue sequentially (rule 6)."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tập")

    params = (body.model_dump(exclude_none=True) if body else {})
    job = Job(episode_id=episode.id, kind="transcribe", status="queued",
              params=params, max_attempts=settings.worker_max_attempts)
    session.add(job)
    episode.status = "queued"
    session.commit()
    return JobOut.model_validate(job)


@router.post("/{episode_id}/export", response_model=JobOut)
def enqueue_export(
    episode_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> JobOut:
    """Queue a regeneration of every export format for this episode."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tập")
    job = Job(episode_id=episode.id, kind="export", status="queued", params={},
              max_attempts=settings.worker_max_attempts)
    session.add(job)
    session.commit()
    return JobOut.model_validate(job)


@router.delete("/{episode_id}")
def delete_episode(
    episode_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> dict:
    """Delete an episode — only if it has no verified utterances.

    The raw JSON under ``/data/raw`` is **kept** on disk regardless (PLAN §0.2, §9):
    deleting a DB row must never delete the master record.
    """
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tập")

    verified = session.scalar(
        select(func.count()).select_from(Utterance)
        .join(Transcript, Transcript.id == Utterance.transcript_id)
        .where(Transcript.episode_id == episode.id,
               Utterance.text_verified.is_not(None))
    ) or 0
    if verified:
        raise HTTPException(
            status_code=409,
            detail=(f"tập có {verified} lượt lời đã duyệt — "
                    "không xóa để tránh mất công sức của người duyệt"),
        )

    session.delete(episode)
    session.commit()
    return {"ok": True, "raw_json_kept": True}


@router.put("/{episode_id}/speakers/{cluster}", response_model=SpeakerLabel)
def set_speaker_label(
    episode_id: uuid.UUID,
    cluster: int,
    body: SpeakerLabel,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> SpeakerLabel:
    """Rename one cluster for this episode (PLAN §9, §0.3 — free text, not identity)."""
    speaker = session.get(Speaker, {"episode_id": episode_id, "cluster": cluster})
    if speaker is None:
        speaker = Speaker(episode_id=episode_id, cluster=cluster)
        session.add(speaker)
    speaker.label = body.label       # stored exactly as typed
    session.commit()
    return SpeakerLabel(label=speaker.label or "")
