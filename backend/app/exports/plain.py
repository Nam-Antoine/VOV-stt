"""Plain text of one episode, without labels: the body of its Google Doc.

    <paragraph>
                                ← one blank line
    <paragraph>\n

Two layers:

``"readable"``  the punctuated reading copy, laid out exactly like the readable
                .txt/.docx/.pdf exports (:func:`app.exports.readable.blocks`).
``"verbatim"``  the corpus text (the verified text where a human typed one, else the
                engine's), unpunctuated and unchanged. Paragraphs break at pauses longer
                than 1.5 s and, inside a long passage, at the first utterance end after
                :data:`app.exports.readable.PARAGRAPH_WORDS` words.

There is no speaker information to label (diarization was removed), so ``labels=False``
is the only mode; it is a parameter so callers state the choice.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from . import paragraphs
from .readable import PARAGRAPH_WORDS, blocks

Layer = Literal["readable", "verbatim"]
LAYERS = ("readable", "verbatim")


def verbatim_blocks(items: list[dict]) -> list[str]:
    """Paragraphs of verbatim text: whole utterances, joined by one space."""
    out: list[str] = []
    for group in paragraphs(items):
        cur: list[str] = []
        n = 0
        for it in group:
            text = it.get("text") or ""
            if not text.strip():
                continue
            cur.append(text)
            n += len(text.split())
            if n >= PARAGRAPH_WORDS:
                out.append(" ".join(cur))
                cur, n = [], 0
        if cur:
            out.append(" ".join(cur))
    return out


def render(items: list[dict], *, layer: Layer, labels: bool = False) -> str:
    """Lay out ``{"start", "end", "text"}`` items (playback order) as plain text."""
    if labels:
        raise ValueError("transcripts carry no speaker information; labels must be off")
    if layer not in LAYERS:
        raise ValueError(f"unknown layer {layer!r}")
    paras = blocks(items) if layer == "readable" else verbatim_blocks(items)
    return "\n\n".join(paras) + "\n"


def render_plain(session: Session, transcript_id: uuid.UUID, layer: Layer,
                 labels: bool = False) -> tuple[str, Layer]:
    """``(text, layer used)`` for one transcript.

    ``readable`` falls back to ``verbatim`` when the punctuation model is not installed.
    Stale readable passages are refreshed first (flushed, not committed).
    """
    from .. import readable as readable_mod
    from ..config import settings
    from ..pipeline import punctuate

    used: Layer = layer
    if layer == "readable":
        if settings.punct_available():
            readable_mod.refresh(session, transcript_id,
                                 punctuate.get(settings.punct_params()))
        else:
            used = "verbatim"
    rows = readable_mod.ordered_utterances(session, transcript_id)
    items = [
        {
            "start": float(u.start_s),
            "end": float(u.end_s),
            "text": u.text_readable if used == "readable" else readable_mod.current_text(u),
        }
        for u in rows
    ]
    return render(items, layer=used, labels=labels), used
