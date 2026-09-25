"""Keep ``utterances.text_readable`` in step with the text people see.

The readable layer is derived from the *current* text of each utterance — the verified
text where a human has typed one, else the ASR text — so it follows edits. It is
recomputed per passage (utterances between pauses, :func:`app.pipeline.merge.passages`),
and only for passages where something changed: a passage is stale when any of its
utterances has no readable text yet, or its ``readable_from`` no longer equals its
current text (an edit, a revert, a split or merge).

Nothing here writes ``text_asr`` or ``text_verified`` (CLAUDE.md rule 1).
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Utterance
from .pipeline import punctuate
from .pipeline.merge import passages

log = logging.getLogger(__name__)


def current_text(u: Utterance) -> str:
    return u.text_verified if u.text_verified is not None else u.text_asr


def is_stale(u: Utterance) -> bool:
    return u.text_readable is None or u.readable_from != current_text(u)


def ordered_utterances(session: Session, transcript_id: uuid.UUID) -> list[Utterance]:
    return list(session.scalars(
        select(Utterance)
        .where(Utterance.transcript_id == transcript_id)
        .order_by(Utterance.start_s, Utterance.i)
    ))


def refresh(session: Session, transcript_id: uuid.UUID,
            punctuator: punctuate.Punctuator) -> int:
    """Recompute stale passages. Returns the number of utterances written. Flushes only."""
    rows = ordered_utterances(session, transcript_id)
    t0 = time.monotonic()
    written = 0
    for group in passages([{"start": float(u.start_s), "end": float(u.end_s)} for u in rows]):
        members = [rows[k] for k in group]
        if not any(is_stale(u) for u in members):
            continue
        texts = [current_text(u) for u in members]
        for u, text, readable in zip(
            members, texts, punctuate.readable_turn(punctuator, texts), strict=True
        ):
            u.text_readable = readable
            u.readable_from = text
            written += 1
    if written:
        session.flush()
        log.info("readable: %d utterances refreshed in %.1f s",
                 written, time.monotonic() - t0)
    return written
