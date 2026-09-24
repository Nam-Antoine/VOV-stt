"""Hotword CRUD and the re-run trigger (PLAN §9, §10 Hotwords page).

Changing hotwords changes future transcripts, so the UI offers "re-run affected
episodes". That re-run only touches episodes with **no verified utterances** — a re-run
must never discard human work (PLAN §0.2).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import Episode, Hotword, Job, Transcript, Utterance
from ..schemas import HotwordIn, HotwordOut, HotwordPatch, HotwordSuggestion, JobOut
from .deps import require_admin, require_editor

router = APIRouter(prefix="/hotwords", tags=["hotwords"])


def _check_encodable(term: str) -> None:
    """400 for a term the model cannot encode — it would be silently inert."""
    from ..pipeline.hotwords import unencodable

    bpe = settings.asr_model_dir / "bpe.model"
    if not bpe.exists():
        return
    bad = unencodable(term, bpe)
    if bad:
        raise HTTPException(
            status_code=400,
            detail=(f"mô hình không nhận được {', '.join(bad)!s}: hãy viết từ khóa bằng "
                    "CHỮ IN HOA đúng như khi đọc, vd. 'ĐÀN BÀ BA MƯƠI CỘNG' "
                    "chứ không phải 'Đàn bà 30+'"),
        )


@router.get("", response_model=list[HotwordOut])
def list_hotwords(
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> list[HotwordOut]:
    return [
        HotwordOut.model_validate(h)
        for h in session.scalars(
            select(Hotword).order_by(Hotword.weight.desc(), Hotword.term)
        )
    ]


@router.get("/suggestions", response_model=list[HotwordSuggestion])
def hotword_suggestions(
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> list[HotwordSuggestion]:
    """Phrases verifiers corrected, most frequent first, not yet hotwords.

    The licence forbids fine-tuning the model (rule 8); hotwords are how its mistakes
    feed back. Terms the model cannot encode are left out — they could never be added.
    """
    from ..corrections import suggestions
    from ..pipeline.hotwords import unencodable

    bpe = settings.asr_model_dir / "bpe.model"
    return [
        HotwordSuggestion(term=s.term, count=s.count, examples=s.examples)
        for s in suggestions(session)
        if not (bpe.exists() and unencodable(s.term, bpe))
    ]


@router.post("", response_model=HotwordOut)
def create_hotword(
    body: HotwordIn,
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> HotwordOut:
    """Store the term exactly as typed; refuse one the model's BPE cannot encode."""
    _check_encodable(body.term)
    existing = session.scalar(select(Hotword).where(Hotword.term == body.term))
    if existing is not None:
        raise HTTPException(status_code=409, detail="từ khóa đã tồn tại")
    hotword = Hotword(term=body.term, weight=body.weight, note=body.note,
                      active=body.active)
    session.add(hotword)
    session.commit()
    return HotwordOut.model_validate(hotword)


@router.patch("/{hotword_id}", response_model=HotwordOut)
def patch_hotword(
    hotword_id: int,
    body: HotwordPatch,
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> HotwordOut:
    hotword = session.get(Hotword, hotword_id)
    if hotword is None:
        raise HTTPException(status_code=404, detail="không tìm thấy từ khóa")
    if body.term is not None:
        _check_encodable(body.term)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(hotword, field, value)
    session.commit()
    return HotwordOut.model_validate(hotword)


@router.delete("/{hotword_id}")
def delete_hotword(
    hotword_id: int,
    hard: bool = False,
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> dict:
    """Deactivate by default; ``?hard=true`` really deletes.

    Deactivating keeps old transcripts explicable: a transcript records the sha256 of
    the hotwords file that produced it, and that is only meaningful while the terms are
    still on record.
    """
    hotword = session.get(Hotword, hotword_id)
    if hotword is None:
        raise HTTPException(status_code=404, detail="không tìm thấy từ khóa")
    if hard:
        session.delete(hotword)
    else:
        hotword.active = False
    session.commit()
    return {"ok": True, "deactivated": not hard}


@router.post("/rerun-all", response_model=list[JobOut])
def rerun_all(
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> list[JobOut]:
    """Enqueue transcribe for every episode with no verified utterances (PLAN §9)."""
    verified_episode_ids = select(Transcript.episode_id).join(
        Utterance, Utterance.transcript_id == Transcript.id
    ).where(Utterance.text_verified.is_not(None)).distinct()

    episodes = list(session.scalars(
        select(Episode)
        .where(Episode.id.not_in(verified_episode_ids),
               Episode.audio_path.is_not(None))
        .order_by(Episode.created_at)
    ))

    jobs = []
    for episode in episodes:
        # Don't pile a second job onto an episode that is already waiting.
        pending = session.scalar(
            select(func.count()).select_from(Job)
            .where(Job.episode_id == episode.id, Job.kind == "transcribe",
                   Job.status.in_(("queued", "running")))
        ) or 0
        if pending:
            continue
        job = Job(episode_id=episode.id, kind="transcribe", status="queued",
                  params={}, max_attempts=settings.worker_max_attempts)
        session.add(job)
        episode.status = "queued"
        jobs.append(job)
    session.commit()
    return [JobOut.model_validate(j) for j in jobs]
