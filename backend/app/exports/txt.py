"""Plain-text export: one utterance per line, the text only (PLAN §1.5).

No speaker column, no timestamps: line ``n`` is utterance ``n`` of the transcript, so two
exports of the same run diff line by line.
"""

from __future__ import annotations

from . import TIER_ASR, utterance_text


def render(doc: dict, *, tier: str = TIER_ASR) -> str:
    """Return the whole episode as text. No wrapping, no punctuation, no casing."""
    lines = [utterance_text(u, tier) for u in doc.get("utterances", [])]
    return "\n".join(lines) + ("\n" if lines else "")


def write(doc: dict, path, *, tier: str = TIER_ASR) -> None:
    """Write UTF-8 (CLAUDE.md rule 3)."""
    from pathlib import Path

    Path(path).write_text(render(doc, tier=tier), encoding="utf-8")
