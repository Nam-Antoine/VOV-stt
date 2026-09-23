"""Verified-tier JSON export (PLAN §0.2, §9).

The raw JSON is immutable. This export layers the human corrections
(``utterances.text_verified``, relabelled speakers, flags) over a *copy* of it and
records which utterances were touched, so a consumer can tell engine output from human
output at a glance.

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


def build(doc: dict, *, overrides: dict | None = None, speakers: dict | None = None) -> dict:
    """Return a new document with the verified layer applied.

    ``overrides`` maps utterance index → ``{"text_verified", "speaker", "flags",
    "verified_by", "verified_at"}``. The input ``doc`` is never mutated.
    """
    out = copy.deepcopy(doc)
    overrides = overrides or {}
    n_verified = 0

    for u in out.get("utterances", []):
        patch = overrides.get(u.get("i")) or overrides.get(str(u.get("i"))) or {}
        u["text_asr"] = u.get("text", "")
        if "speaker" in patch and patch["speaker"] is not None:
            u["speaker"] = patch["speaker"]
        u["flags"] = list(patch.get("flags") or u.get("flags") or [])
        u["text_verified"] = patch.get("text_verified", u.get("text_verified"))
        u["verified_by"] = patch.get("verified_by", u.get("verified_by"))
        u["verified_at"] = patch.get("verified_at", u.get("verified_at"))
        if u["text_verified"] is not None:
            n_verified += 1
        # `text` is the tier-resolved text: verified when present, else ASR.
        u["text"] = utterance_text(u, TIER_VERIFIED)

    out["tier"] = TIER_VERIFIED
    out["speakers"] = dict(speakers or {})
    out["verification"] = {
        "utterances_total": len(out.get("utterances", [])),
        "utterances_verified": n_verified,
        "exported_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
    }
    return out


def render(doc: dict, *, overrides: dict | None = None,
           speakers: dict | None = None) -> str:
    """Serialise with ``ensure_ascii=False`` — CLAUDE.md rule 3."""
    return json.dumps(
        build(doc, overrides=overrides, speakers=speakers),
        ensure_ascii=False, indent=2,
    ) + "\n"


def write(doc: dict, path, *, overrides: dict | None = None,
          speakers: dict | None = None) -> None:
    Path(path).write_text(
        render(doc, overrides=overrides, speakers=speakers), encoding="utf-8"
    )
