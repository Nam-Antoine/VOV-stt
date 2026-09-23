"""SubRip export (PLAN §1.5) — one cue per utterance.

Subtitles are a convenience view, not a corpus artefact, but the same rule holds: the
text in a cue is the utterance text unchanged. No line-length wrapping that would insert
breaks into the token stream, no sentence-casing.
"""

from __future__ import annotations

from . import TIER_ASR, speaker_label, utterance_text


def timestamp(seconds: float) -> str:
    """``HH:MM:SS,mmm`` — SubRip uses a comma before the milliseconds."""
    if seconds is None or seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render(doc: dict, *, tier: str = TIER_ASR, speakers: dict | None = None,
           with_speaker: bool = True) -> str:
    """Return the whole episode as SubRip text."""
    blocks = []
    for n, u in enumerate(doc.get("utterances", []), start=1):
        text = utterance_text(u, tier)
        if with_speaker:
            text = f"[{speaker_label(speakers, u.get('speaker'))}] {text}"
        blocks.append(
            f"{n}\n{timestamp(u.get('start'))} --> {timestamp(u.get('end'))}\n{text}\n"
        )
    return "\n".join(blocks)


def write(doc: dict, path, *, tier: str = TIER_ASR, speakers: dict | None = None) -> None:
    from pathlib import Path

    Path(path).write_text(render(doc, tier=tier, speakers=speakers), encoding="utf-8")
