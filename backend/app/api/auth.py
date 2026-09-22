"""Single shared password → signed session cookie (PLAN §6 auth v1).

Not a user system. One team, one password, one cookie. Anything more (roles, SSO,
per-user audit) is out of scope for v1 — but ``utterance_edits.editor`` already has a
column for it, so the audit trail is not blocked by this choice.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from ..schemas import LoginRequest, LoginResponse
from . import not_implemented

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response) -> LoginResponse:
    """Compare against ``APP_PASSWORD`` and set the signed session cookie.

    TODO(T3): constant-time compare with ``secrets.compare_digest``; sign the cookie
    with ``SECRET_KEY`` (itsdangerous); ``httponly=True``, ``samesite="lax"``,
    ``secure=True`` behind Caddy.
    """
    raise not_implemented("auth")


@router.post("/logout", response_model=LoginResponse)
def logout(response: Response) -> LoginResponse:
    """Clear the session cookie."""
    raise not_implemented("auth")
