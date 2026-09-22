"""Hotword CRUD and the re-run trigger (PLAN §9, §10 Hotwords page).

Changing hotwords changes future transcripts, so the UI offers "re-run affected
episodes". That re-run only touches episodes with **no verified utterances** — a re-run
must never discard human work (PLAN §0.2).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import HotwordIn, HotwordOut, HotwordPatch, JobOut
from . import not_implemented

router = APIRouter(prefix="/hotwords", tags=["hotwords"])


@router.get("", response_model=list[HotwordOut])
def list_hotwords(session: Session = Depends(get_session)) -> list[HotwordOut]:
    """TODO(T3)."""
    raise not_implemented("hotword listing")


@router.post("", response_model=HotwordOut)
def create_hotword(
    body: HotwordIn, session: Session = Depends(get_session)
) -> HotwordOut:
    """TODO(T3): store the term exactly as typed — casing and diacritics included."""
    raise not_implemented("hotword create")


@router.patch("/{hotword_id}", response_model=HotwordOut)
def patch_hotword(
    hotword_id: int, body: HotwordPatch, session: Session = Depends(get_session)
) -> HotwordOut:
    """TODO(T3)."""
    raise not_implemented("hotword update")


@router.delete("/{hotword_id}")
def delete_hotword(hotword_id: int, session: Session = Depends(get_session)) -> dict:
    """TODO(T3): prefer ``active=false`` over a hard delete so old transcripts stay
    explicable."""
    raise not_implemented("hotword delete")


@router.post("/rerun-all", response_model=list[JobOut])
def rerun_all(session: Session = Depends(get_session)) -> list[JobOut]:
    """Enqueue transcribe for every episode with no verified utterances (PLAN §9)."""
    raise not_implemented("hotword re-run")
