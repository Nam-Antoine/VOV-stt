"""Default project helper — every episode belongs to a project (PLAN projects)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Project

#: "Đàn bà 30+", created by alembic 0009_projects; it keeps the Sheet the owner already
#: has the link to, so old uploads and scripts that name no project still land here.
DEFAULT_PROJECT_SLUG = "dan-ba-30"


def default_project(session: Session) -> Project:
    project = session.scalar(select(Project).where(Project.slug == DEFAULT_PROJECT_SLUG))
    if project is not None:
        return project
    project = session.scalar(select(Project).order_by(Project.created_at).limit(1))
    if project is None:
        raise RuntimeError("no project exists — run `alembic upgrade head`")
    return project
