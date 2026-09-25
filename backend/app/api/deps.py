"""Shared FastAPI dependencies: the session cookie, roles, and episode lookup.

With ``AUTH_ENABLED=false`` (the default) there is no login: every request acts as an
admin named ``OPEN_EDITOR``. Otherwise the cookie is a signed ``{"uid", "sv"}`` pair.
Every request re-reads the user row, so disabling an account, changing its role or
resetting its password (all of which bump ``session_version``) takes effect on the next
request, not when the cookie expires.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import Episode, Transcript, User

# v2: v1 cookies carried only a free-text editor name and must not be accepted.
SESSION_SALT = "vnstt-session-v2"


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=SESSION_SALT)


def issue_session(user: User) -> str:
    return serializer().dumps({"uid": str(user.id), "sv": user.session_version})


def read_session(token: str) -> dict:
    """Verify and decode; raises ``BadSignature``/``SignatureExpired`` when invalid."""
    return serializer().loads(token, max_age=settings.session_max_age_s)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def open_user() -> User:
    """Stand-in account when login is switched off (``AUTH_ENABLED=false``)."""
    return User(id=uuid.UUID(int=0), username=settings.open_editor, role="admin",
                is_active=True, session_version=0)


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    """The signed-in, active user whose session is still current, or 401."""
    if not settings.auth_enabled:
        return open_user()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _unauthorized("chưa đăng nhập")
    try:
        data = read_session(token)
        user = session.get(User, uuid.UUID(str(data.get("uid"))))
    except SignatureExpired:
        raise _unauthorized("phiên đăng nhập đã hết hạn") from None
    except (BadSignature, ValueError):
        raise _unauthorized("phiên đăng nhập không hợp lệ") from None
    if user is None or not user.is_active or data.get("sv") != user.session_version:
        raise _unauthorized("phiên đăng nhập không còn hiệu lực")
    return user


def require_editor(user: User = Depends(current_user)) -> str:
    """Any signed-in account; returns the username recorded against edits."""
    return user.username


def require_admin(user: User = Depends(current_user)) -> str:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="chỉ quản trị viên được làm việc này")
    return user.username


def get_episode_or_404(episode_id: uuid.UUID,
                       session: Session = Depends(get_session)) -> Episode:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tập")
    return episode


# --- the readable layer ------------------------------------------------------------

def require_punct_model() -> None:
    if not settings.punct_available():
        raise HTTPException(status_code=503, detail="chưa cài mô hình thêm dấu câu")


def refresh_readable_layer(session: Session, transcript: Transcript) -> int:
    """Bring the punctuated layer up to date (stale passages only) and commit.

    503 without the punctuation model. Returns the number of utterances rewritten.
    """
    from .. import readable as readable_mod
    from ..pipeline import punctuate

    require_punct_model()
    written = readable_mod.refresh(session, transcript.id,
                                   punctuate.get(settings.punct_params()))
    session.commit()
    return written
