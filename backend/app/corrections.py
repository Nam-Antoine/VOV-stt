"""Hotword suggestions from verifiers' corrections: the model's mistakes, fed back.

The ASR model may not be fine-tuned (CC BY-NC-ND 4.0, CLAUDE.md rule 8), so this is the
licence-safe loop: when a verifier fixes a word, the corrected phrase is offered as a
hotword, and every later transcription is biased towards it. Nothing is added
automatically; an admin accepts each suggestion on the Hotwords page.

Read-only over the corpus: both texts are compared, neither is changed (rule 1).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Episode, Hotword, Transcript, Utterance

#: A correction longer than this is a rewrite of the passage, not a misheard term.
MAX_SPAN_WORDS = 5

_WORD = re.compile(r"\w+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text or "")


def correction_spans(asr: str, verified: str) -> list[tuple[str, str]]:
    """``[(heard, corrected), ...]``: the words a verifier replaced or added.

    Casing and punctuation are not corrections. A one-word fix keeps a neighbour on
    each side ("là đàn bà", not "đàn"): a lone short word makes a poor hotword.
    """
    a, b = _words(asr), _words(verified)
    matcher = SequenceMatcher(a=[w.casefold() for w in a], b=[w.casefold() for w in b],
                              autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op not in ("replace", "insert") or j2 - j1 > MAX_SPAN_WORDS:
            continue
        if j2 - j1 == 1:
            j1, j2 = max(0, j1 - 1), min(len(b), j2 + 1)
            i1, i2 = max(0, i1 - 1), min(len(a), i2 + 1)
        out.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return out


@dataclass
class Suggestion:
    term: str                       # as the model spells: capitals, full diacritics
    count: int = 0
    examples: list[dict] = field(default_factory=list)


def suggest(rows: Iterable[tuple[str, str, uuid.UUID, str]],
            existing: set[str], *, max_examples: int = 3) -> list[Suggestion]:
    """Aggregate ``(text_asr, text_verified, episode_id, title)`` rows into suggestions."""
    found: dict[str, Suggestion] = {}
    for asr, verified, episode_id, title in rows:
        for heard, corrected in correction_spans(asr, verified):
            term = corrected.upper()
            if not term or term in existing:
                continue
            s = found.setdefault(term, Suggestion(term=term))
            s.count += 1
            if len(s.examples) < max_examples:
                s.examples.append({"episode_id": str(episode_id), "title": title or "",
                                   "heard": heard, "corrected": corrected})
    return sorted(found.values(), key=lambda s: (-s.count, s.term))


def suggestions(session: Session, *, limit: int = 50) -> list[Suggestion]:
    """Suggestions from every current transcript's verified corrections."""
    rows = session.execute(
        select(Utterance.text_asr, Utterance.text_verified, Episode.id, Episode.title)
        .join(Transcript, Transcript.id == Utterance.transcript_id)
        .join(Episode, Episode.id == Transcript.episode_id)
        .where(Transcript.is_current.is_(True), Utterance.text_verified.is_not(None),
               Utterance.text_verified != Utterance.text_asr)
        .order_by(Episode.air_date, Utterance.i)
    ).all()
    existing = {t.upper() for t in session.scalars(select(Hotword.term))}
    return suggest(rows, existing)[:limit]
