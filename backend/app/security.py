"""Password hashing and login throttling.

Hashing uses stdlib ``hashlib.scrypt`` (memory-hard, no extra dependency). The stored
form is ``scrypt$n$r$p$salt$hash`` so the cost can be raised later without breaking
existing hashes: ``needs_rehash`` tells the login handler to upgrade on the next login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

# ~32 MB and ~0.15 s per hash on this box: slow for a guesser, fine for a login.
_N, _R, _P = 2**15, 8, 1
_DKLEN = 32
_MAXMEM = 64 * 1024 * 1024

MIN_PASSWORD_LENGTH = 10


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


# At most two hashes at once: FastAPI runs sync handlers on a 40-thread pool, and 40
# parallel login attempts x 32 MB would be a cheap way to squeeze a 6 GB box.
_hashing = threading.BoundedSemaphore(2)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    with _hashing:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                              dklen=_DKLEN, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        got = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, base64.b64decode(digest))


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(f"scrypt${_N}${_R}${_P}$")


# A real hash of a random password: unknown usernames are checked against it so the
# response time doesn't reveal which usernames exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problem(password: str) -> str | None:
    """Why a new password is refused, in Vietnamese for the UI; ``None`` if it's fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự"
    if len(password) > 256:
        return "mật khẩu quá dài"
    return None


class LoginThrottle:
    """Lock a key (client IP, or username) after too many failures in a window.

    In-memory: the api runs as one uvicorn process, and a restart clearing the counters
    is acceptable. Both the IP and the username are counted, so one address can't
    spray many accounts and many addresses can't hammer one account unnoticed.
    """

    def __init__(self, max_failures: int = 5, window_s: float = 15 * 60,
                 clock=time.monotonic) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self._clock = clock
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        kept = [t for t in self._fails.get(key, []) if now - t < self.window_s]
        if kept:
            self._fails[key] = kept
        else:
            self._fails.pop(key, None)
        return kept

    def retry_after(self, *keys: str) -> int:
        """Seconds until the caller may try again; 0 means allowed now."""
        with self._lock:
            now = self._clock()
            wait = 0.0
            for key in keys:
                recent = self._recent(key, now)
                if len(recent) >= self.max_failures:
                    wait = max(wait, recent[-self.max_failures] + self.window_s - now)
            return int(wait) + 1 if wait > 0 else 0

    def fail(self, *keys: str) -> None:
        with self._lock:
            now = self._clock()
            for key in keys:
                self._fails.setdefault(key, []).append(now)
                self._recent(key, now)

    def succeed(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._fails.pop(key, None)


login_throttle = LoginThrottle()
