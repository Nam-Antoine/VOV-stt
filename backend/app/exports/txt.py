"""Plain-text export: one utterance per line, ``SPEAKER<TAB>text`` (PLAN §1.5).

The same shape as ``pilot/reference.txt``, so a transcript and the hand-verified
reference can be diffed directly.
"""

from __future__ import annotations

from . import TIER_ASR, speaker_label, utterance_text


def render(doc: dict, *, tier: str = TIER_ASR, speakers: dict | None = None) -> str:
    """Return the whole episode as text. No wrapping, no punctuation, no casing."""
    lines = []
    for u in doc.get("utterances", []):
        lines.append(f"{speaker_label(speakers, u.get('speaker'))}\t{utterance_text(u, tier)}")
    return "\n".join(lines) + ("\n" if lines else "")


def write(doc: dict, path, *, tier: str = TIER_ASR, speakers: dict | None = None) -> None:
    """Write UTF-8 (CLAUDE.md rule 3)."""
    from pathlib import Path

    Path(path).write_text(render(doc, tier=tier, speakers=speakers), encoding="utf-8")
