"""Export formats derived from the raw JSON (PLAN §0.2, §9).

Every export is *regenerated* from the raw JSON plus the verified layer. None of them is
a source of truth, and none of them may alter text: an exporter that tidies punctuation
or drops a repeated word corrupts the corpus silently.
``app/tests/test_no_normalisation.py`` holds every exporter to that.

Two tiers, selected by ``tier``:

``"asr"``       the engine's own text (``utterances[].text``)
``"verified"``  ``text_verified`` where a human has supplied one, else the ASR text

No export carries speaker information: there is no diarization, and paragraphs break on
pauses (:data:`app.pipeline.merge.PASSAGE_GAP_S`).
"""

from __future__ import annotations

TIER_ASR = "asr"
TIER_VERIFIED = "verified"


def utterance_text(utterance: dict, tier: str = TIER_ASR) -> str:
    """The text for one utterance in the requested tier, verbatim.

    ``text_verified`` is only used when it is not ``None``; an empty string is a
    deliberate human edit (an utterance marked as containing no speech) and is honoured.
    """
    if tier == TIER_VERIFIED:
        verified = utterance.get("text_verified")
        if verified is not None:
            return verified
    return utterance.get("text", "")


def paragraphs(utterances: list[dict]) -> list[list[dict]]:
    """Consecutive utterances grouped into paragraphs at pauses longer than 1.5 s.

    A grouping only: no utterance text is read or changed.
    """
    from ..pipeline.merge import passages

    return [[utterances[k] for k in group] for group in passages(utterances)]
