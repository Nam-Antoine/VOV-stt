"""Read-only facts about the Google repository, for the Exports page (Task 8).

No auth UI: signing in happens once, on the owner's laptop (README "Google repository").
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..google_repo.sheet import sheet_url
from ..models import Project
from ..projects import default_project
from ..schemas import GoogleRepoOut
from .deps import require_editor

router = APIRouter(prefix="/google-repo", tags=["google"])


@router.get("", response_model=GoogleRepoOut)
def google_repo(
    project_id: uuid.UUID | None = Query(None),
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> GoogleRepoOut:
    if not settings.google_repo_enabled:
        return GoogleRepoOut(enabled=False)
    project = session.get(Project, project_id) if project_id else default_project(session)
    if project is None:
        raise HTTPException(status_code=404, detail="không tìm thấy dự án")
    return GoogleRepoOut(
        enabled=True,
        sheet_url=sheet_url(project.google_sheet_id) if project.google_sheet_id else None,
        last_full_sync=project.google_last_full_sync,
    )
