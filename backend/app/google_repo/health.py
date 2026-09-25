"""``google_repo`` in ``/api/health``: disabled | ok | token_invalid | error: <reason>.

Checking means loading (and maybe refreshing) the token, a network call, so the answer
is cached for a few minutes. Never includes a token, a secret or an exception message
that could carry one — only an exception's type name.
"""

from __future__ import annotations

import time

from ..config import settings

CACHE_S = 300.0
_cache: tuple[float, str] | None = None


def repo_health(*, now: float | None = None) -> str:
    global _cache
    if not settings.google_repo_enabled:
        return "disabled"
    now = time.monotonic() if now is None else now
    if _cache is not None and now - _cache[0] < CACHE_S:
        return _cache[1]
    from .auth import GoogleAuthError, get_credentials

    try:
        get_credentials()
        value = "ok"
    except GoogleAuthError:
        value = "token_invalid"
    except Exception as exc:  # noqa: BLE001 — health reports, never raises
        value = f"error: {type(exc).__name__}"
    _cache = (now, value)
    return value
