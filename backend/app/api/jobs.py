"""Queue view, retries and log tail (PLAN §9, §10 Jobs page)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import Job
from ..schemas import JobLog, JobOut
from .deps import require_editor

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _out(job: Job) -> JobOut:
    """The job plus its episode's name, so the queue reads as episodes, not ids."""
    out = JobOut.model_validate(job)
    if job.episode is not None:
        out.episode_title = job.episode.title or job.episode.slug
    return out


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str | None = Query(None),
    limit: int = Query(50, le=500),
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> list[JobOut]:
    """Newest first, optional status filter."""
    stmt = (select(Job).options(selectinload(Job.episode))
            .order_by(Job.created_at.desc()).limit(limit))
    if status:
        stmt = stmt.where(Job.status == status)
    return [_out(j) for j in session.scalars(stmt)]


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> JobOut:
    """Reset a failed job to ``queued`` and clear ``locked_at``."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tác vụ")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="tác vụ đang chạy")
    job.status = "queued"
    job.locked_at = None
    job.finished_at = None
    job.error = None
    # Give the retry a fresh budget; otherwise a job that already burned its attempts
    # is re-queued only to be failed again on the first claim.
    job.attempts = 0
    session.commit()
    return _out(job)


@router.get("/{job_id}/log", response_model=JobLog)
def job_log(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> JobLog:
    """``jobs.log``; the UI polls this every 2 s while a job is running."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tác vụ")
    return JobLog(id=job.id, log=job.log or job.error or "")
