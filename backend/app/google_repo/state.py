"""``google_repo_state`` key/value helpers: folder_id, sheet_id, sheet_sha256…"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import GoogleRepoState

FOLDER_ID = "folder_id"
SHEET_ID = "sheet_id"
SHEET_SHA256 = "sheet_sha256"
LAST_FULL_SYNC = "last_full_sync"


def get(session: Session, key: str) -> str | None:
    row = session.get(GoogleRepoState, key)
    return row.value if row else None


def put(session: Session, key: str, value: str | None) -> None:
    row = session.get(GoogleRepoState, key)
    if row is None:
        session.add(GoogleRepoState(key=key, value=value))
    else:
        row.value = value
    session.flush()
