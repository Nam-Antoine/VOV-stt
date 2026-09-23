"""Idempotent seed data — ``make seed`` / ``python -m app.seed``.

The initial migration already seeds hotwords; this module exists so the list can be
topped up later without a new migration, and so the pilot's chosen knobs (PLAN §11 T2)
can be written into ``settings``.

Nothing here overwrites an operator's edits: terms are inserted ``ON CONFLICT DO
NOTHING``, and settings are only written when a key is absent unless ``--force``.
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import session_scope
from .models import Hotword, Setting

log = logging.getLogger("seed")

# The model's vocabulary is UPPERCASE spoken form, so terms are written that way — a
# mixed-case term encodes to <unk> and biases nothing. Kept in step with
# alembic/versions/0001_initial.py + 0002_hotwords_model_form.py (PLAN §8).
HOTWORD_SEED: list[tuple[str, float, str]] = [
    ("ĐÀN BÀ BA MƯƠI CỘNG", 1.5, "programme name (Đàn bà 30+), as spoken"),
    ("VOV2", 1.5, "station"),
    ("THANH HUYỀN", 1.5, "MC"),
    ("DI LI", 1.5, "guest — nhà văn"),
    ("HOÀNG ANH TÚ", 1.5, "recurring guest"),
    ("ĐỖ ANH VŨ", 1.5, "recurring guest"),
    ("QUẢN CHỒNG", 1.0, "recurring topic"),
    ("GIỮ CHỒNG", 1.0, "recurring topic"),
    ("GIỮ LỬA", 1.0, "recurring topic"),
    ("NGOẠI TÌNH", 1.0, "recurring topic"),
    ("TÂM SỰ", 1.0, "recurring topic"),
    ("HÔN NHÂN", 1.0, "recurring topic"),
    ("CHUNG THỦY", 1.0, "recurring topic"),
    ("LY HÔN", 1.0, "recurring topic"),
    ("GIA ĐÌNH", 1.0, "recurring topic"),
]

#: Pipeline defaults. The pilot (PLAN §4.3) replaces these with measured choices; until
#: T2 signs off they are PLAN §2/§3 values, not tuned ones.
SETTINGS_SEED: dict[str, dict] = {
    "asr": {
        "decoding_method": "modified_beam_search",
        "max_active_paths": 4,
        "blank_penalty": 0.25,
        "int8": True,
        "num_threads": 3,
        "_source": "PLAN §2 defaults — not yet confirmed by the pilot (T2)",
    },
    "vad": {
        "threshold": 0.3, "min_speech_s": 0.1, "min_silence_s": 0.4,
        "pad_s": 0.35, "merge_gap_s": 0.3, "max_segment_s": 25.0,
        "_source": "PLAN §3 defaults",
    },
    "diarization": {
        "threshold": 0.7, "num_clusters": 0,
        "min_duration_on": 0.3, "min_duration_off": 0.5,
        "window_shift_ratio": 0.2,
        "_source": "PLAN §3 defaults; window_shift_ratio benchmarked 2026-09-23",
    },
}


def seed_hotwords(session, *, terms=HOTWORD_SEED) -> int:  # noqa: ANN001
    """Insert missing terms; returns how many rows were actually inserted.

    ``rowcount`` is unreliable for ``ON CONFLICT DO NOTHING`` (psycopg reports -1), so
    the count comes from a RETURNING clause instead of being guessed.
    """
    stmt = (
        pg_insert(Hotword)
        .values([
            {"term": term, "weight": weight, "note": note, "active": True}
            for term, weight, note in terms
        ])
        .on_conflict_do_nothing(index_elements=["term"])
        .returning(Hotword.id)
    )
    return len(session.execute(stmt).scalars().all())


def seed_settings(session, *, force: bool = False) -> int:  # noqa: ANN001
    """Write the default knobs. Without ``force``, existing keys are left alone."""
    written = 0
    for key, value in SETTINGS_SEED.items():
        stmt = pg_insert(Setting).values(key=key, value=value)
        stmt = (
            stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value})
            if force
            else stmt.on_conflict_do_nothing(index_elements=["key"])
        )
        written += len(session.execute(stmt.returning(Setting.key)).scalars().all())
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force-settings", action="store_true",
                    help="overwrite existing settings rows with the defaults")
    args = ap.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(levelname)-7s %(message)s")

    with session_scope() as session:
        n_hot = seed_hotwords(session)
        n_set = seed_settings(session, force=args.force_settings)
    log.info("seeded %d hotwords, %d settings rows", n_hot, n_set)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
