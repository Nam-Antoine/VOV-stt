"""Verified-tier JSON export (PLAN §0.2, §9).

The raw JSON is immutable. This export layers the human corrections
(``utterances.text_verified``, flags) over a *copy* of it and records which utterances
were touched, so a consumer can tell engine output from human output at a glance.

Transcripts made before diarization was removed carry speaker clusters in their raw
JSON; this copy drops them (the ``diarization`` block and every ``speaker`` field), so
no export has speaker information. The raw JSON itself is untouched.

``text_asr`` is always carried through beside ``text_verified``: losing the engine's
original would break the hotword feedback loop (PLAN §10) and make the corpus
unauditable.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from . import TIER_VERIFIED, utterance_text


def build(doc: dict, *, overrides: dict | None = None) -> dict:
    """Return a new document with the verified layer applied.

    ``overrides`` maps utterance index → ``{"text_verified", "flags", "verified_by",
    "verified_at"}``. The input ``doc`` is never mutated.
    """
    out = copy.deepcopy(doc)
    out.pop("diarization", None)
    out.pop("speakers", None)
    for w in out.get("words", []):
        w.pop("speaker", None)
    overrides = overrides or {}
    n_verified = 0

    for u in out.get("utterances", []):
        patch = overrides.get(u.get("i")) or overrides.get(str(u.get("i"))) or {}
        u.pop("speaker", None)
        u["text_asr"] = u.get("text", "")
        u["flags"] = list(patch.get("flags") or u.get("flags") or [])
        u["text_verified"] = patch.get("text_verified", u.get("text_verified"))
        u["verified_by"] = patch.get("verified_by", u.get("verified_by"))
        u["verified_at"] = patch.get("verified_at", u.get("verified_at"))
        if u["text_verified"] is not None:
            n_verified += 1
        # `text` is the tier-resolved text: verified when present, else ASR.
        u["text"] = utterance_text(u, TIER_VERIFIED)

    out["tier"] = TIER_VERIFIED
    out["verification"] = {
        "utterances_total": len(out.get("utterances", [])),
        "utterances_verified": n_verified,
        "exported_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
    }
    return out


def render(doc: dict, *, overrides: dict | None = None) -> str:
    """Serialise with ``ensure_ascii=False`` — CLAUDE.md rule 3."""
    return json.dumps(
        build(doc, overrides=overrides),
        ensure_ascii=False, indent=2,
    ) + "\n"


def write(doc: dict, path, *, overrides: dict | None = None) -> None:
    Path(path).write_text(render(doc, overrides=overrides), encoding="utf-8")
