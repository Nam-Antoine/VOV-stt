"""Per-user login: hashing, throttling, sessions and roles (no database needed)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import deps
from app.config import settings
from app.db import get_session
from app.main import app
from app.models import User
from app.security import (
    LoginThrottle,
    hash_password,
    login_throttle,
    needs_rehash,
    password_problem,
    verify_password,
)


def make_user(username="nam", role="editor", password="mat-khau-dai-du", **kw) -> User:
    return User(id=uuid.uuid4(), username=username, role=role, is_active=True,
                session_version=0, password_hash=hash_password(password), **kw)


class FakeSession:
    """Just enough of a Session for the auth paths: one user, looked up by id or name."""

    def __init__(self, *users: User) -> None:
        self.users = list(users)
        self.commits = 0

    def get(self, model, key):
        return next((u for u in self.users if u.id == key), None)

    def scalar(self, stmt):
        wanted = stmt.compile(compile_kwargs={"literal_binds": True}).string
        return next((u for u in self.users if f"'{u.username}'" in wanted), None)

    def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def accounts_on(monkeypatch):
    """These tests cover the account system; the deployed default is login off."""
    monkeypatch.setattr(settings, "auth_enabled", True)


@pytest.fixture
def client_with():
    def build(*users):
        fake = FakeSession(*users)
        app.dependency_overrides[get_session] = lambda: fake
        login_throttle._fails.clear()
        return TestClient(app), fake
    yield build
    app.dependency_overrides.clear()
    login_throttle._fails.clear()


# --- hashing ------------------------------------------------------------------

def test_hash_roundtrip_and_salted():
    h1, h2 = hash_password("mot hai ba bon"), hash_password("mot hai ba bon")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password("mot hai ba bon", h1)
    assert not verify_password("mot hai ba bo", h1)
    assert not needs_rehash(h1)


def test_verify_rejects_garbage_hashes():
    assert not verify_password("x", "")
    assert not verify_password("x", "plain-text-password")
    assert not verify_password("x", "bcrypt$1$2$3$aa$bb")


def test_password_rules():
    assert password_problem("ngắn") is not None
    assert password_problem("đủ dài rồi nhé") is None


# --- throttle -----------------------------------------------------------------

def test_throttle_locks_after_max_failures_then_expires():
    now = [0.0]
    t = LoginThrottle(max_failures=3, window_s=60, clock=lambda: now[0])
    for _ in range(3):
        assert t.retry_after("ip:1") == 0
        t.fail("ip:1")
    assert t.retry_after("ip:1") > 0
    assert t.retry_after("ip:2") == 0  # other clients unaffected
    now[0] = 61
    assert t.retry_after("ip:1") == 0


def test_throttle_success_clears():
    t = LoginThrottle(max_failures=2)
    t.fail("user:a")
    t.succeed("user:a")
    t.fail("user:a")
    assert t.retry_after("user:a") == 0


# --- session dependency -----------------------------------------------------------

class Req:
    def __init__(self, token):
        self.cookies = {settings.session_cookie_name: token} if token else {}


def test_current_user_accepts_a_fresh_cookie():
    u = make_user()
    assert deps.current_user(Req(deps.issue_session(u)), FakeSession(u)) is u


@pytest.mark.parametrize("change", ["disable", "bump", "missing", "old_cookie", "none"])
def test_current_user_rejects(change):
    u = make_user()
    token = deps.issue_session(u)
    session = FakeSession(u)
    if change == "disable":
        u.is_active = False
    elif change == "bump":
        u.session_version += 1  # password reset / role change elsewhere
    elif change == "missing":
        session.users.clear()
    elif change == "old_cookie":  # a v1 shared-password cookie
        from itsdangerous import URLSafeTimedSerializer
        token = URLSafeTimedSerializer(settings.secret_key,
                                       salt="vnstt-session-v1").dumps({"editor": "x"})
    elif change == "none":
        token = None
    with pytest.raises(HTTPException) as exc:
        deps.current_user(Req(token), session)
    assert exc.value.status_code == 401


def test_require_admin():
    assert deps.require_admin(make_user(role="admin")) == "nam"
    with pytest.raises(HTTPException) as exc:
        deps.require_admin(make_user(role="editor"))
    assert exc.value.status_code == 403


# --- HTTP ---------------------------------------------------------------------

def test_login_me_logout(client_with):
    client, fake = client_with(make_user(display_name="Nam"))
    r = client.post("/api/auth/login",
                    json={"username": " NAM ", "password": "mat-khau-dai-du"})
    assert r.status_code == 200, r.text
    assert r.json() == {"username": "nam", "display_name": "Nam", "role": "editor",
                        "auth_enabled": True}
    assert "httponly" in r.headers["set-cookie"].lower()
    assert fake.users[0].last_login_at is not None
    assert client.get("/api/auth/me").json()["username"] == "nam"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_look_the_same(client_with):
    client, _ = client_with(make_user())
    a = client.post("/api/auth/login", json={"username": "nam", "password": "sai-mat-khau"})
    b = client.post("/api/auth/login", json={"username": "ai-do", "password": "sai-mat-khau"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_disabled_user_cannot_log_in(client_with):
    u = make_user()
    u.is_active = False
    client, _ = client_with(u)
    r = client.post("/api/auth/login", json={"username": "nam", "password": "mat-khau-dai-du"})
    assert r.status_code == 401


def test_login_is_throttled(client_with):
    client, _ = client_with(make_user())
    for _ in range(login_throttle.max_failures):
        client.post("/api/auth/login", json={"username": "nam", "password": "sai-mat-khau"})
    r = client.post("/api/auth/login", json={"username": "nam", "password": "mat-khau-dai-du"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_change_password_keeps_this_session_only(client_with):
    u = make_user()
    client, _ = client_with(u)
    client.post("/api/auth/login", json={"username": "nam", "password": "mat-khau-dai-du"})
    other = deps.issue_session(u)  # another browser, signed in earlier
    r = client.post("/api/auth/password", json={"current_password": "sai",
                                                "new_password": "mat-khau-moi-dai"})
    assert r.status_code == 400
    r = client.post("/api/auth/password", json={"current_password": "mat-khau-dai-du",
                                                "new_password": "mat-khau-moi-dai"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    with pytest.raises(HTTPException):
        deps.current_user(Req(other), FakeSession(u))
    assert verify_password("mat-khau-moi-dai", u.password_hash)


def test_editor_cannot_manage_users_or_hotwords(client_with):
    client, _ = client_with(make_user())
    client.post("/api/auth/login", json={"username": "nam", "password": "mat-khau-dai-du"})
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/hotwords", json={"term": "x"}).status_code == 403


def test_admin_cannot_lock_themselves_out(client_with):
    admin = make_user(username="boss", role="admin")
    client, _ = client_with(admin)
    client.post("/api/auth/login", json={"username": "boss", "password": "mat-khau-dai-du"})
    r = client.patch(f"/api/users/{admin.id}", json={"is_active": False})
    assert r.status_code == 400
    r = client.patch(f"/api/users/{admin.id}", json={"role": "editor"})
    assert r.status_code == 400
    assert admin.is_active and admin.role == "admin"


def test_admin_reset_signs_the_user_out(client_with):
    admin, ed = make_user(username="boss", role="admin"), make_user()
    client, _ = client_with(admin, ed)
    client.post("/api/auth/login", json={"username": "boss", "password": "mat-khau-dai-du"})
    r = client.patch(f"/api/users/{ed.id}", json={"password": "ngan"})
    assert r.status_code == 400
    r = client.patch(f"/api/users/{ed.id}", json={"password": "mat-khau-moi-dai"})
    assert r.status_code == 200, r.text
    assert ed.session_version == 1


# --- login switched off (the default) ---------------------------------------------

def test_open_mode_needs_no_cookie_and_hides_accounts(client_with, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    client, _ = client_with(make_user(username="boss", role="admin"))
    me = client.get("/api/auth/me").json()
    assert me["auth_enabled"] is False and me["role"] == "admin"
    assert me["username"] == settings.open_editor
    assert client.get("/api/users").status_code == 404
    r = client.post("/api/auth/login", json={"username": "boss", "password": "mat-khau-dai-du"})
    assert r.status_code == 404
    anyone = deps.current_user(Req(None), FakeSession())
    assert deps.require_editor(anyone) == settings.open_editor


def test_login_refuses_to_start_with_a_placeholder_secret(monkeypatch):
    from app.main import on_startup

    monkeypatch.setattr(settings, "secret_key", "dev-only-change-me")
    with pytest.raises(RuntimeError):
        on_startup()
