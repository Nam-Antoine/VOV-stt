"""Queue view, retries and log tail (PLAN §9, §10 Jobs page)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import JobLog, JobOut
from . import not_implemented

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str | None = Query(None), session: Session = Depends(get_session)
) -> list[JobOut]:
    """TODO(T3): newest first, optional status filter."""
    raise not_implemented("job listing")


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> JobOut:
    """TODO(T3): reset a failed job to ``queued`` and clear ``locked_at``."""
    raise not_implemented("job retry")


@router.get("/{job_id}/log", response_model=JobLog)
def job_log(job_id: uuid.UUID, session: Session = Depends(get_session)) -> JobLog:
    """TODO(T3): return ``jobs.log``; the UI polls this every 2 s while running."""
    raise not_implemented("job log")
