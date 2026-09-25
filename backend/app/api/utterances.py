"""The human-editable layer (PLAN §9, §10).

Every write here goes through the same rule: **store what the verifier typed, byte for
byte**. No trimming, no smart quotes, no sentence casing, no spell correction
(CLAUDE.md rule 1). The one thing the API adds is an append-only row in
``utterance_edits``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Utterance, UtteranceEdit, Word
from ..schemas import UtteranceOut, UtterancePatch, UtteranceSplit
from .deps import require_editor

router = APIRouter(prefix="/utterances", tags=["utterances"])


def _get(session: Session, utterance_id: uuid.UUID) -> Utterance:
    """The utterance, for a write. Every route in this module writes."""
    utterance = session.get(Utterance, utterance_id)
    if utterance is None:
        raise HTTPException(status_code=404, detail="không tìm thấy lượt lời")
    return utterance


def _log_edit(session: Session, utterance: Utterance, before: str | None,
              after: str | None, editor: str) -> None:
    """Append to the audit log. Never UPDATE or DELETE a row here (PLAN §8)."""
    session.add(UtteranceEdit(utterance_id=utterance.id, before=before,
                              after=after, editor=editor))


@router.patch("/{utterance_id}", response_model=UtteranceOut)
def patch_utterance(
    utterance_id: uuid.UUID,
    body: UtterancePatch,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> UtteranceOut:
    """Update text_verified / flags / bounds.

    ``text_verified=""`` is a real edit meaning "no speech here"; only ``None`` means
    untouched, so the presence of the field in the payload is what matters, not its
    truthiness.
    """
    utterance = _get(session, utterance_id)
    patch = body.model_dump(exclude_unset=True)

    if "text_verified" in patch:
        before = utterance.text_verified
        after = patch["text_verified"]      # stored exactly as sent
        if before != after:
            utterance.text_verified = after
            utterance.verified_by = editor
            utterance.verified_at = datetime.now(UTC)
            _log_edit(session, utterance, before, after, editor)

    if "flags" in patch and patch["flags"] is not None:
        utterance.flags = list(patch["flags"])
    if "start_s" in patch and patch["start_s"] is not None:
        utterance.start_s = float(patch["start_s"])
    if "end_s" in patch and patch["end_s"] is not None:
        utterance.end_s = float(patch["end_s"])

    session.commit()
    return UtteranceOut.model_validate(utterance)


@router.post("/{utterance_id}/split", response_model=list[UtteranceOut])
def split_utterance(
    utterance_id: uuid.UUID,
    body: UtteranceSplit,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> list[UtteranceOut]:
    """Split at ``at_word_i`` — e.g. where one utterance runs across a turn change.

    The split point is a **word index**, so the text is divided on a boundary the engine
    itself produced. Neither half is re-joined or re-spaced: each is the space-join of
    its own words, exactly as ``merge.build_utterances`` would have produced it.
    """
    utterance = _get(session, utterance_id)
    words = list(session.scalars(
        select(Word)
        .where(Word.transcript_id == utterance.transcript_id,
               Word.start_s >= utterance.start_s,
               Word.start_s < utterance.end_s)
        .order_by(Word.i)
    ))
    if not words:
        raise HTTPException(status_code=409, detail="lượt lời này không có từ nào")

    head = [w for w in words if w.i < body.at_word_i]
    tail = [w for w in words if w.i >= body.at_word_i]
    if not head or not tail:
        raise HTTPException(
            status_code=400,
            detail=f"at_word_i={body.at_word_i} nằm ngoài lượt lời này "
                   f"({words[0].i}..{words[-1].i})",
        )

    if utterance.text_verified is not None:
        # Splitting would have to guess where the human's text divides. Refuse rather
        # than silently mangle it.
        raise HTTPException(
            status_code=409,
            detail="lượt lời đã có văn bản được duyệt; hãy khôi phục trước khi tách",
        )

    # Shift every later utterance up by one to keep `i` contiguous.
    session.execute(
        update(Utterance)
        .where(Utterance.transcript_id == utterance.transcript_id,
               Utterance.i > utterance.i)
        .values(i=Utterance.i + 1)
    )

    tail_utterance = Utterance(
        transcript_id=utterance.transcript_id,
        i=utterance.i + 1,
        start_s=float(tail[0].start_s),
        end_s=utterance.end_s,
        text_asr=" ".join(w.text for w in tail),
        text_verified=None,
        flags=list(utterance.flags or []),
    )
    utterance.end_s = float(head[-1].end_s or head[-1].start_s)
    utterance.text_asr = " ".join(w.text for w in head)
    session.add(tail_utterance)
    session.commit()
    return [UtteranceOut.model_validate(utterance),
            UtteranceOut.model_validate(tail_utterance)]


@router.post("/{utterance_id}/merge-next", response_model=UtteranceOut)
def merge_next(
    utterance_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> UtteranceOut:
    """Join this utterance with the next one.

    Concatenated with a single space — the same join ``merge.build_utterances`` uses, so
    a merged utterance is indistinguishable from one the pipeline produced.
    """
    utterance = _get(session, utterance_id)
    nxt = session.scalar(
        select(Utterance)
        .where(Utterance.transcript_id == utterance.transcript_id,
               Utterance.i == utterance.i + 1)
    )
    if nxt is None:
        raise HTTPException(status_code=409, detail="không có lượt lời tiếp theo")

    before = utterance.text_verified
    utterance.text_asr = f"{utterance.text_asr} {nxt.text_asr}"
    if utterance.text_verified is not None or nxt.text_verified is not None:
        left = (utterance.text_verified if utterance.text_verified is not None
                else utterance.text_asr)
        right = nxt.text_verified if nxt.text_verified is not None else nxt.text_asr
        utterance.text_verified = f"{left} {right}"
        _log_edit(session, utterance, before, utterance.text_verified, editor)
        utterance.verified_by = editor
        utterance.verified_at = datetime.now(UTC)
    utterance.end_s = nxt.end_s
    utterance.flags = list({*(utterance.flags or []), *(nxt.flags or [])})

    session.delete(nxt)
    session.flush()
    session.execute(
        update(Utterance)
        .where(Utterance.transcript_id == utterance.transcript_id,
               Utterance.i > nxt.i)
        .values(i=Utterance.i - 1)
    )
    session.commit()
    return UtteranceOut.model_validate(utterance)


@router.post("/{utterance_id}/revert", response_model=UtteranceOut)
def revert_utterance(
    utterance_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> UtteranceOut:
    """Set ``text_verified = NULL`` — back to the engine's text.

    This still appends an edit row: reverting is an edit, and the audit log has to show
    that a human decided the engine was right.
    """
    utterance = _get(session, utterance_id)
    before = utterance.text_verified
    if before is not None:
        _log_edit(session, utterance, before, None, editor)
    utterance.text_verified = None
    utterance.verified_by = None
    utterance.verified_at = None
    session.commit()
    return UtteranceOut.model_validate(utterance)
