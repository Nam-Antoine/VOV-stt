"""Projects: one Drive folder + index Sheet per programme (PLAN §9 extension).

"Đàn bà 30+" (alembic 0009_projects) is project #1 and keeps the folder and Sheet it
already had. Creating or renaming a project queues a ``google_sync`` job so its folder
and Sheet appear (or are renamed) without waiting for an episode.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..google_repo import sync as google_sync
from ..google_repo.sheet import sheet_url
from ..models import Episode, Project, Transcript, Utterance
from ..schemas import ProjectCreate, ProjectOut, ProjectPatch
from ..slugs import slugify, unique_slug
from .deps import require_admin, require_editor

router = APIRouter(prefix="/projects", tags=["projects"])


def _counts(session: Session, project_ids: list[uuid.UUID]) -> dict:
    """``{project_id: (n_episodes, n_transcribed, n_verified, verified_seconds)}``."""
    if not project_ids:
        return {}
    episode_counts = dict(session.execute(
        select(Episode.project_id, func.count())
        .where(Episode.project_id.in_(project_ids)).group_by(Episode.project_id)
    ).all())
    transcribed = dict(session.execute(
        select(Episode.project_id, func.count(func.distinct(Episode.id)))
        .select_from(Episode)
        .join(Transcript, Transcript.episode_id == Episode.id)
        .where(Episode.project_id.in_(project_ids), Transcript.is_current.is_(True))
        .group_by(Episode.project_id)
    ).all())
    verified = session.execute(
        select(Episode.project_id, func.count(func.distinct(Utterance.id)),
              func.coalesce(func.sum(Utterance.end_s - Utterance.start_s), 0))
        .select_from(Episode)
        .join(Transcript, Transcript.episode_id == Episode.id)
        .join(Utterance, Utterance.transcript_id == Transcript.id)
        .where(Episode.project_id.in_(project_ids), Transcript.is_current.is_(True),
              Utterance.text_verified.is_not(None))
        .group_by(Episode.project_id)
    ).all()
    verified_counts = {r[0]: (int(r[1]), float(r[2])) for r in verified}
    return {
        pid: (
            int(episode_counts.get(pid, 0)),
            int(transcribed.get(pid, 0)),
            verified_counts.get(pid, (0, 0.0))[0],
            round(verified_counts.get(pid, (0, 0.0))[1] / 3600.0, 2),
        )
        for pid in project_ids
    }


def _out(project: Project, counts: tuple[int, int, int, float]) -> ProjectOut:
    n_episodes, n_transcribed, n_verified, hours_verified = counts
    return ProjectOut.model_validate(project).model_copy(update={
        "sheet_url": sheet_url(project.google_sheet_id) if project.google_sheet_id else None,
        "n_episodes": n_episodes, "n_transcribed": n_transcribed,
        "n_verified": n_verified, "hours_verified": hours_verified,
    })


@router.get("", response_model=list[ProjectOut])
def list_projects(
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> list[ProjectOut]:
    projects = list(session.scalars(select(Project).order_by(Project.created_at)))
    counts = _counts(session, [p.id for p in projects])
    return [_out(p, counts.get(p.id, (0, 0, 0, 0.0))) for p in projects]


@router.post("", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> ProjectOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="tên dự án không được để trống")
    slug = unique_slug(session, Project.slug, slugify(name, fallback="du-an"))
    project = Project(slug=slug, name=name, description=body.description)
    session.add(project)
    session.commit()
    google_sync.enqueue_project(session, project.id)
    session.commit()
    return _out(project, (0, 0, 0, 0.0))


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> ProjectOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="không tìm thấy dự án")
    counts = _counts(session, [project.id])
    return _out(project, counts.get(project.id, (0, 0, 0, 0.0)))


@router.patch("/{project_id}", response_model=ProjectOut)
def patch_project(
    project_id: uuid.UUID,
    body: ProjectPatch,
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> ProjectOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="không tìm thấy dự án")
    renamed = False
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="tên dự án không được để trống")
        renamed = name != project.name
        project.name = name
    if body.description is not None:
        project.description = body.description
    session.commit()
    if renamed:
        google_sync.enqueue_project(session, project.id)
        session.commit()
    counts = _counts(session, [project.id])
    return _out(project, counts.get(project.id, (0, 0, 0, 0.0)))


@router.delete("/{project_id}")
def delete_project(
    project_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_admin),
) -> dict:
    """Only when the project has no episodes. Removes the DB row only — the Drive
    folder and Sheet, if any were ever created, are left exactly as they are
    (CLAUDE.md rule 11: code never deletes anything in Google Drive)."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="không tìm thấy dự án")
    n = session.scalar(
        select(func.count()).select_from(Episode).where(Episode.project_id == project.id)
    ) or 0
    if n:
        raise HTTPException(
            status_code=409,
            detail=f"dự án có {n} tập — hãy chuyển hoặc xóa hết các tập trước",
        )
    session.delete(project)
    session.commit()
    return {"ok": True, "drive_kept": True}
