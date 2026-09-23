"""Load a raw JSON document into ``transcripts`` / ``words`` / ``utterances`` (PLAN §8).

The raw JSON on disk is the master record (PLAN §0.2); these rows are a *derived*,
rebuildable projection of it. That direction matters:

* a re-run inserts a **new** transcript row and flips the old one's ``is_current``;
  nothing is updated in place, and no raw file is ever rewritten;
* ``utterances.text_asr`` is a frozen copy of the engine's text, and ``text_verified``
  starts NULL. Human corrections attach to the transcript they were made against, so a
  re-run never silently re-points someone's work at different audio timings.

Nothing here alters text. ``text_asr`` is the raw JSON's ``text`` byte for byte
(CLAUDE.md rule 1).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import Episode, Speaker, Transcript, Utterance, Word

log = logging.getLogger("loader")


def raw_json_dest(raw_dir: Path, episode_slug: str, transcript_id: uuid.UUID) -> Path:
    """``/data/raw/<slug>/<transcript_id>.json`` (PLAN §6)."""
    return Path(raw_dir) / episode_slug / f"{transcript_id}.json"


def load_transcript(
    session: Session,
    *,
    episode: Episode,
    doc: dict,
    raw_json_path: Path,
    transcript_id: uuid.UUID | None = None,
    hotwords_sha256: str | None = None,
    speakers_pending: bool = False,
) -> Transcript:
    """Insert one transcript and its derived rows. Returns the new transcript.

    ``speakers_pending`` marks the ASR-only transcript the worker publishes before
    diarization finishes (see :func:`app.pipeline.run.preliminary_doc`).
    """
    engine_block = doc.get("engine") or {}
    transcript = Transcript(
        id=transcript_id or uuid.uuid4(),
        episode_id=episode.id,
        engine=engine_block.get("name") or "unknown",
        engine_version=engine_block.get("sherpa_onnx_version"),
        params=engine_block.get("params"),
        hotwords_sha256=hotwords_sha256
        or (engine_block.get("params") or {}).get("hotwords_sha256"),
        raw_json_path=str(raw_json_path),
        is_current=True,
        speakers_pending=speakers_pending,
    )

    # Demote the previous current transcript before inserting the new one, so there is
    # never a moment with two rows claiming to be current.
    session.execute(
        update(Transcript)
        .where(Transcript.episode_id == episode.id, Transcript.is_current.is_(True))
        .values(is_current=False)
    )
    session.add(transcript)
    session.flush()

    words = doc.get("words") or []
    if words:
        session.execute(
            Word.__table__.insert(),
            [
                {
                    "transcript_id": transcript.id,
                    "i": int(w["i"]),
                    "text": w.get("text", ""),      # verbatim
                    "start_s": float(w["start"]),
                    "end_s": None if w.get("end") is None else float(w["end"]),
                    "conf": w.get("conf"),
                    "speaker": int(w.get("speaker", -1)),
                }
                for w in words
            ],
        )

    utterances = doc.get("utterances") or []
    if utterances:
        session.execute(
            Utterance.__table__.insert(),
            [
                {
                    "id": uuid.uuid4(),
                    "transcript_id": transcript.id,
                    "i": int(u["i"]),
                    "speaker": int(u.get("speaker", -1)),
                    "start_s": float(u["start"]),
                    "end_s": float(u["end"]),
                    "text_asr": u.get("text", ""),  # frozen, verbatim
                    "text_verified": None,          # untouched until a human types
                    "flags": [],
                }
                for u in utterances
            ],
        )

    # A speakers-pending preview only has cluster -1; registering it would leave a
    # stale "unknown speaker" row behind once the final clusters arrive.
    if not speakers_pending:
        upsert_speakers(session, episode_id=episode.id,
                        clusters={int(u.get("speaker", -1)) for u in utterances})

    log.info("loaded transcript %s: %d words, %d utterances",
             transcript.id, len(words), len(utterances))
    return transcript


def upsert_speakers(session: Session, *, episode_id: uuid.UUID,
                    clusters: set[int]) -> None:
    """Ensure a ``speakers`` row exists per cluster, without clobbering labels.

    A verifier may already have named cluster 0 "MC Thanh Huyền" from an earlier run.
    ``ON CONFLICT DO NOTHING`` keeps that label; PLAN §0.3 is explicit that the label is
    the human's, not the system's.
    """
    clusters = {c for c in clusters if c is not None}
    if not clusters:
        return
    session.execute(
        pg_insert(Speaker)
        .values([{"episode_id": episode_id, "cluster": c, "label": None}
                 for c in sorted(clusters)])
        .on_conflict_do_nothing(index_elements=["episode_id", "cluster"])
    )


def current_transcript(session: Session, episode_id: uuid.UUID) -> Transcript | None:
    return session.scalar(
        select(Transcript)
        .where(Transcript.episode_id == episode_id, Transcript.is_current.is_(True))
        .order_by(Transcript.created_at.desc())
    )


def utterance_counts(session: Session, transcript_id: uuid.UUID) -> tuple[int, int]:
    """``(total, verified)`` for one transcript."""
    total = session.scalar(
        select(func.count()).select_from(Utterance)
        .where(Utterance.transcript_id == transcript_id)
    ) or 0
    verified = session.scalar(
        select(func.count()).select_from(Utterance)
        .where(Utterance.transcript_id == transcript_id,
               Utterance.text_verified.is_not(None))
    ) or 0
    return int(total), int(verified)


def speaker_labels(session: Session, episode_id: uuid.UUID) -> dict[int, str]:
    """``{cluster: label}`` for the clusters that have been named."""
    rows = session.execute(
        select(Speaker.cluster, Speaker.label).where(Speaker.episode_id == episode_id)
    ).all()
    return {int(c): label for c, label in rows if label}


def overrides_for(session: Session, transcript_id: uuid.UUID) -> dict[int, dict]:
    """The verified layer, keyed by utterance index, for the export renderers."""
    rows = session.execute(
        select(Utterance.i, Utterance.text_verified, Utterance.speaker,
               Utterance.flags, Utterance.verified_by, Utterance.verified_at)
        .where(Utterance.transcript_id == transcript_id)
        .order_by(Utterance.i)
    ).all()
    return {
        int(i): {
            "text_verified": text_verified,
            "speaker": int(speaker),
            "flags": list(flags or []),
            "verified_by": verified_by,
            "verified_at": verified_at.isoformat() if verified_at else None,
        }
        for i, text_verified, speaker, flags, verified_by, verified_at in rows
    }
