"""Account CLI — mainly for the first admin, before anyone can log in to the Users page.

    docker compose exec api python -m app.users create <username> [--admin] [--name "…"]
    docker compose exec api python -m app.users reset-password <username>
    docker compose exec api python -m app.users list

The password is prompted for; leave it empty to generate one, which is printed once.
"""

from __future__ import annotations

import argparse
import getpass
import re
import secrets
import sys

from sqlalchemy import func, select

from .db import session_scope
from .models import User
from .schemas import USERNAME_PATTERN
from .security import hash_password, password_problem


def _ask_password() -> tuple[str, bool]:
    if not sys.stdin.isatty():
        return secrets.token_urlsafe(12), True
    pw = getpass.getpass("Mật khẩu (để trống = tạo ngẫu nhiên): ")
    if not pw:
        return secrets.token_urlsafe(12), True
    if getpass.getpass("Nhập lại: ") != pw:
        sys.exit("mật khẩu không khớp")
    problem = password_problem(pw)
    if problem:
        sys.exit(problem)
    return pw, False


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.users")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("username")
    c.add_argument("--admin", action="store_true")
    c.add_argument("--name")
    r = sub.add_parser("reset-password")
    r.add_argument("username")
    sub.add_parser("list")
    args = ap.parse_args(argv)

    with session_scope() as session:
        if args.cmd == "list":
            for u in session.scalars(select(User).order_by(User.created_at)):
                state = "" if u.is_active else "  (đã khoá)"
                print(f"{u.username:24} {u.role:7} {u.display_name or ''}{state}")
            return

        username = args.username.strip().lower()
        user = session.scalar(select(User).where(func.lower(User.username) == username))
        if args.cmd == "create":
            if not re.match(USERNAME_PATTERN, username):
                sys.exit("tên đăng nhập: 2–32 ký tự a-z, 0-9, . _ -")
            if user:
                sys.exit(f"{username} đã tồn tại")
            pw, generated = _ask_password()
            session.add(User(username=username, display_name=args.name,
                             role="admin" if args.admin else "editor",
                             password_hash=hash_password(pw)))
        else:
            if not user:
                sys.exit(f"không có tài khoản {username}")
            pw, generated = _ask_password()
            user.password_hash = hash_password(pw)
            user.session_version += 1
            user.is_active = True

    print(f"OK: {username}")
    if generated:
        print(f"Mật khẩu: {pw}")


if __name__ == "__main__":
    main()
