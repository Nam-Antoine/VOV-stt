"""Speaker cluster labels (PLAN §9, §0.3).

A label is per-episode free text a verifier typed. It is not an identity, it does not
carry across episodes, and nothing here tries to match a voice to a person — the vox-pop
voices are identifiable private individuals and that is deliberate policy, not an
oversight (PLAN §0.3).

The canonical route is ``PUT /episodes/{id}/speakers/{cluster}`` in
:mod:`app.api.episodes`; this router holds the read side.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import SpeakerOut
from . import not_implemented

router = APIRouter(tags=["speakers"])


@router.get("/episodes/{episode_id}/speakers", response_model=list[SpeakerOut])
def list_speakers(
    episode_id: uuid.UUID, session: Session = Depends(get_session)
) -> list[SpeakerOut]:
    """TODO(T3): clusters present in the current transcript, with their labels."""
    raise not_implemented("speaker listing")
