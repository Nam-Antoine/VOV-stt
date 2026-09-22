"""The human-editable layer (PLAN §9, §10).

Every write here goes through the same rule: **store what the verifier typed, byte for
byte**. No trimming, no smart quotes, no sentence casing, no spell correction
(CLAUDE.md rule 1). The one thing the API adds is an append-only row in
``utterance_edits``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import UtteranceOut, UtterancePatch, UtteranceSplit
from . import not_implemented

router = APIRouter(prefix="/utterances", tags=["utterances"])


@router.patch("/{utterance_id}", response_model=UtteranceOut)
def patch_utterance(
    utterance_id: uuid.UUID,
    body: UtterancePatch,
    session: Session = Depends(get_session),
) -> UtteranceOut:
    """Update text_verified / speaker / flags / bounds.

    TODO(T3): write ``utterance_edits`` (before, after, editor, at) in the same
    transaction, and set ``verified_at``. ``text_verified=""`` is a real edit meaning
    "no speech here"; only ``None`` means untouched.
    """
    raise not_implemented("utterance edit")


@router.post("/{utterance_id}/split", response_model=list[UtteranceOut])
def split_utterance(
    utterance_id: uuid.UUID,
    body: UtteranceSplit,
    session: Session = Depends(get_session),
) -> list[UtteranceOut]:
    """Split at ``at_word_i`` — used when diarization merged two speakers.

    TODO(T3): reindex the following utterances; both halves keep their own slice of
    ``word_ids`` so no word is orphaned.
    """
    raise not_implemented("utterance split")


@router.post("/{utterance_id}/merge-next", response_model=UtteranceOut)
def merge_next(
    utterance_id: uuid.UUID, session: Session = Depends(get_session)
) -> UtteranceOut:
    """Join this utterance with the next one.

    TODO(T3): concatenate with a single space — the same join ``merge.build_utterances``
    uses, so a merged utterance is indistinguishable from one the pipeline produced.
    """
    raise not_implemented("utterance merge")


@router.post("/{utterance_id}/revert", response_model=UtteranceOut)
def revert_utterance(
    utterance_id: uuid.UUID, session: Session = Depends(get_session)
) -> UtteranceOut:
    """Set ``text_verified = NULL`` — back to the engine's text.

    TODO(T3): this still appends an edit row; reverting is an edit.
    """
    raise not_implemented("utterance revert")
