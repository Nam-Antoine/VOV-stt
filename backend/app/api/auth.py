"""Single shared password → signed session cookie (PLAN §6 auth v1).

Not a user system. One team, one password, one cookie. Anything more (roles, SSO,
per-user audit) is out of scope for v1 — but ``utterance_edits.editor`` already has a
column for it, so the audit trail is not blocked by this choice.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status

from ..config import settings
from ..schemas import LoginRequest, LoginResponse
from .deps import issue_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    """Compare against ``APP_PASSWORD`` and set the signed session cookie."""
    # Constant-time: a timing side channel on a shared password is cheap to avoid.
    if not secrets.compare_digest(body.password, settings.app_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="wrong password")
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issue_session(body.editor or "verifier"),
        max_age=settings.session_max_age_s,
        httponly=True,
        samesite="lax",
        # Only mark Secure when the request actually arrived over TLS: with a plain
        # http:// dev origin a Secure cookie is silently dropped and login "succeeds"
        # while every later request is 401.
        secure=request.url.scheme == "https",
        path="/",
    )
    return LoginResponse(ok=True)


@router.post("/logout", response_model=LoginResponse)
def logout(response: Response) -> LoginResponse:
    """Clear the session cookie."""
    response.delete_cookie(settings.session_cookie_name, path="/")
    return LoginResponse(ok=True)


@router.get("/me", response_model=LoginResponse)
def me(request: Request) -> LoginResponse:
    """Cheap 'am I signed in?' probe for the SPA's route guard."""
    from itsdangerous import BadSignature, SignatureExpired

    from .deps import read_session

    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="not signed in")
    try:
        read_session(token)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="invalid session") from None
    return LoginResponse(ok=True)
