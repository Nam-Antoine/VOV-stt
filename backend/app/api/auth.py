"""Per-user login → signed session cookie.

Accounts are created by an admin (``/api/users``) or, for the first admin, by
``python -m app.users``. There is no public sign-up. Failed logins are throttled per
client IP and per username (``app.security.LoginThrottle``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import User
from ..schemas import LoginRequest, LoginResponse, Me, PasswordChange
from ..security import (
    DUMMY_HASH,
    hash_password,
    login_throttle,
    needs_rehash,
    password_problem,
    verify_password,
)
from .deps import current_user, issue_session

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(request: Request, response: Response, user: User) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issue_session(user),
        max_age=settings.session_max_age_s,
        httponly=True,
        samesite="lax",
        # Only mark Secure when the request actually arrived over TLS: with a plain
        # http:// dev origin a Secure cookie is silently dropped and login "succeeds"
        # while every later request is 401.
        secure=request.url.scheme == "https",
        path="/",
    )


@router.post("/login", response_model=Me)
def login(body: LoginRequest, request: Request, response: Response,
          session: Session = Depends(get_session)) -> Me:
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail="đăng nhập đang tắt")
    username = body.username.strip().lower()
    keys = (f"ip:{request.client.host if request.client else '?'}", f"user:{username}")
    wait = login_throttle.retry_after(*keys)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"sai quá nhiều lần — thử lại sau {max(1, round(wait / 60))} phút",
            headers={"Retry-After": str(wait)},
        )

    user = session.scalar(select(User).where(func.lower(User.username) == username))
    # Hash even for unknown users so timing doesn't reveal which usernames exist.
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not (user and ok and user.is_active):
        login_throttle.fail(*keys)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="sai tên đăng nhập hoặc mật khẩu")

    login_throttle.succeed(*keys)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    session.commit()
    set_session_cookie(request, response, user)
    return Me(username=user.username, display_name=user.display_name, role=user.role)


@router.post("/logout", response_model=LoginResponse)
def logout(response: Response) -> LoginResponse:
    """Clear the session cookie."""
    response.delete_cookie(settings.session_cookie_name, path="/")
    return LoginResponse(ok=True)


@router.get("/me", response_model=Me)
def me(user: User = Depends(current_user)) -> Me:
    """Who is signed in — the SPA's route guard and role check."""
    return Me(username=user.username, display_name=user.display_name, role=user.role,
              auth_enabled=settings.auth_enabled)


@router.post("/password", response_model=LoginResponse)
def change_password(body: PasswordChange, request: Request, response: Response,
                    user: User = Depends(current_user),
                    session: Session = Depends(get_session)) -> LoginResponse:
    """Change your own password. Other sessions are signed out; this one is kept."""
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail="đăng nhập đang tắt")
    # Throttled like login: a stolen cookie must not buy unlimited password guesses.
    key = f"user:{user.username}"
    wait = login_throttle.retry_after(key)
    if wait:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="sai quá nhiều lần — thử lại sau",
                            headers={"Retry-After": str(wait)})
    if not verify_password(body.current_password, user.password_hash):
        login_throttle.fail(key)
        raise HTTPException(status_code=400, detail="mật khẩu hiện tại không đúng")
    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    user.password_hash = hash_password(body.new_password)
    user.session_version += 1
    session.commit()
    set_session_cookie(request, response, user)
    return LoginResponse(ok=True)
