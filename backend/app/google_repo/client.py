"""Google API plumbing: the three services, retries, and the Docs write rate limit.

Every call goes through :func:`call`, so tests can hand in fake services (Task 9) and
no code path reaches the network on its own.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("google_repo")

#: Retried with exponential backoff; anything else fails at once.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_TRIES = 5


@dataclass
class Google:
    drive: Any
    docs: Any
    sheets: Any
    #: Injected by tests so retries and the rate limit do not really sleep.
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _last_write: float | None = field(default=None, repr=False)

    def throttle(self, min_interval_s: float = 1.1) -> None:
        """At most one Doc write per 1.1 s (the Docs API allows 60 writes/min/user)."""
        now = self.clock()
        if self._last_write is not None and now - self._last_write < min_interval_s:
            self.sleep(min_interval_s - (now - self._last_write))
            now = self.clock()
        self._last_write = now


def connect() -> Google:
    """Real services for the owning account (raises GoogleAuthError when signed out)."""
    from googleapiclient.discovery import build

    from .auth import get_credentials

    creds = get_credentials()
    return Google(
        drive=build("drive", "v3", credentials=creds, cache_discovery=False),
        docs=build("docs", "v1", credentials=creds, cache_discovery=False),
        sheets=build("sheets", "v4", credentials=creds, cache_discovery=False),
    )


def status_of(exc: BaseException) -> int | None:
    resp = getattr(exc, "resp", None)
    try:
        return int(getattr(resp, "status", None))
    except (TypeError, ValueError):
        return None


def call(g: Google, request) -> dict:  # noqa: ANN001 — a googleapiclient HttpRequest
    """Execute ``request``, retrying 429/5xx up to 5 tries with exponential backoff."""
    from googleapiclient.errors import HttpError

    for attempt in range(1, MAX_TRIES + 1):
        try:
            return request.execute()
        except HttpError as exc:
            status = status_of(exc)
            if status not in RETRY_STATUSES or attempt == MAX_TRIES:
                raise
            delay = 2.0 ** attempt
            log.warning("google: HTTP %s, retrying in %.0f s (%d/%d)",
                        status, delay, attempt, MAX_TRIES)
            g.sleep(delay)
    raise AssertionError("unreachable")


def short_error(exc: BaseException) -> str:
    """One line for ``last_error``: the HTTP status and reason, never a token."""
    status = status_of(exc)
    reason = getattr(exc, "reason", None) or type(exc).__name__
    text = f"HTTP {status}: {reason}" if status else f"{type(exc).__name__}: {exc}"
    return text.splitlines()[0][:300]
