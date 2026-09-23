"""Export formats derived from the raw JSON (PLAN §0.2, §9).

Every export is *regenerated* from the raw JSON plus the verified layer. None of them is
a source of truth, and none of them may alter text: an exporter that tidies punctuation
or drops a repeated word corrupts the corpus silently.
``app/tests/test_no_normalisation.py`` holds every exporter to that.

Two tiers, selected by ``tier``:

``"asr"``       the engine's own text (``utterances[].text``)
``"verified"``  ``text_verified`` where a human has supplied one, else the ASR text
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


def speaker_label(speakers: dict | None, cluster: int) -> str:
    """Human label for a cluster, falling back to ``SPEAKER_00`` style.

    Labels are per-episode free text a verifier typed (PLAN §0.3) — never an identity
    the system inferred.
    """
    if speakers:
        label = speakers.get(cluster) or speakers.get(str(cluster))
        if label:
            return label
    if cluster is None or cluster < 0:
        return "SPEAKER_UNKNOWN"
    return f"SPEAKER_{cluster:02d}"
