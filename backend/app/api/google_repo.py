"""Read-only facts about the Google repository, for the Exports page (Task 8).

No auth UI: signing in happens once, on the owner's laptop (README "Google repository").
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..google_repo import state
from ..google_repo.sheet import sheet_url
from ..schemas import GoogleRepoOut
from .deps import require_editor

router = APIRouter(prefix="/google-repo", tags=["google"])


@router.get("", response_model=GoogleRepoOut)
def google_repo(
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> GoogleRepoOut:
    if not settings.google_repo_enabled:
        return GoogleRepoOut(enabled=False)
    sheet_id = state.get(session, state.SHEET_ID)
    return GoogleRepoOut(
        enabled=True,
        sheet_url=sheet_url(sheet_id) if sheet_id else None,
        last_full_sync=state.get(session, state.LAST_FULL_SYNC),
    )
