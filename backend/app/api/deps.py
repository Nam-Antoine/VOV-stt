"""Shared FastAPI dependencies: the session cookie and episode lookup.

Auth v1 is one shared password for one team (PLAN §6). The cookie carries no user
identity beyond a free-text editor name, which is what lands in
``utterance_edits.editor`` — enough for an audit trail without building a user system.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import Episode

SESSION_SALT = "vnstt-session-v1"


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=SESSION_SALT)


def issue_session(editor: str = "verifier") -> str:
    """Sign a session payload. ``editor`` is recorded against edits made in it."""
    return serializer().dumps({"editor": editor})


def read_session(token: str) -> dict:
    """Verify and decode; raises ``BadSignature``/``SignatureExpired`` when invalid."""
    return serializer().loads(token, max_age=settings.session_max_age_s)


def require_editor(request: Request) -> str:
    """Validate the signed session cookie and return the editor name.

    The cookie's name comes from settings, so it is read off the request rather than
    declared as a ``Cookie(...)`` parameter with a hard-coded alias.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="not signed in")
    try:
        data = read_session(token)
    except SignatureExpired:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="session expired") from None
    except BadSignature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="invalid session") from None
    return str(data.get("editor") or "verifier")


def get_episode_or_404(episode_id: uuid.UUID,
                       session: Session = Depends(get_session)) -> Episode:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="episode not found")
    return episode
