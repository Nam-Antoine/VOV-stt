"""Account management — admins only.

Accounts are disabled, never deleted: ``utterance_edits.editor`` refers to usernames,
and the audit trail should keep pointing at someone who existed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import hash_password, password_problem
from .deps import current_user, require_admin


def _accounts_on() -> None:
    # With login switched off there are no accounts to manage, and an open endpoint
    # that creates them would be pointless at best.
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail="đăng nhập đang tắt")


router = APIRouter(prefix="/users", tags=["users"],
                   dependencies=[Depends(_accounts_on), Depends(require_admin)])


def _check_password(password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)


def _active_admins(session: Session) -> int:
    # Row locks, held to commit: two admins demoting each other at the same moment
    # would otherwise both see "2 left" and leave none.
    return len(session.scalars(
        select(User.id).where(User.role == "admin", User.is_active.is_(True))
        .with_for_update()
    ).all())


@router.get("", response_model=list[UserOut])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at, User.username)))


@router.post("", response_model=UserOut)
def create_user(body: UserCreate, session: Session = Depends(get_session)) -> User:
    _check_password(body.password)
    if session.scalar(select(User).where(func.lower(User.username) == body.username)):
        raise HTTPException(status_code=409, detail="tên đăng nhập đã tồn tại")
    user = User(username=body.username, display_name=(body.display_name or "").strip() or None,
                role=body.role, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate,
                me: User = Depends(current_user),
                session: Session = Depends(get_session)) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tài khoản")

    fields = body.model_fields_set
    losing_admin = user.role == "admin" and user.is_active and (
        (body.role is not None and body.role != "admin")
        or (body.is_active is False)
    )
    if losing_admin and user.id == me.id:
        raise HTTPException(status_code=400,
                            detail="không thể tự bỏ quyền hoặc tự khoá tài khoản của mình")
    if losing_admin and _active_admins(session) <= 1:
        raise HTTPException(status_code=400, detail="phải còn ít nhất một quản trị viên")

    signs_out = False
    if "display_name" in fields:
        user.display_name = (body.display_name or "").strip() or None
    if body.role is not None and body.role != user.role:
        user.role = body.role
        signs_out = True
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        signs_out = True
    if body.password is not None:
        _check_password(body.password)
        user.password_hash = hash_password(body.password)
        signs_out = True
    if signs_out:
        user.session_version += 1
    session.commit()
    return user
