"""Initial schema (PLAN §8) + hotwords seed.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

EPISODE_STATUSES = (
    "ingested", "queued", "processing", "transcribed", "verifying", "verified", "failed",
)
JOB_KINDS = ("transcribe", "export")
JOB_STATUSES = ("queued", "running", "done", "failed")

#: PLAN §8 seed list: show name, station, the regular voices, and the recurring
#: subject-matter vocabulary the acoustic model is most likely to mangle.
HOTWORD_SEED: list[tuple[str, float, str]] = [
    ("Đàn bà 30+", 1.5, "programme name"),
    ("VOV2", 1.5, "station"),
    ("Thanh Huyền", 1.5, "MC"),
    ("Di Li", 1.5, "guest — nhà văn"),
    ("Hoàng Anh Tú", 1.5, "recurring guest"),
    ("Đỗ Anh Vũ", 1.5, "recurring guest"),
    ("quản chồng", 1.0, "recurring topic"),
    ("giữ chồng", 1.0, "recurring topic"),
    ("giữ lửa", 1.0, "recurring topic"),
    ("ngoại tình", 1.0, "recurring topic"),
    ("tâm sự", 1.0, "recurring topic"),
    ("hôn nhân", 1.0, "recurring topic"),
    ("chung thủy", 1.0, "recurring topic"),
    ("ly hôn", 1.0, "recurring topic"),
    ("gia đình", 1.0, "recurring topic"),
]


def _in(column: str, values) -> str:
    return f"{column} in (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("air_date", sa.Date()),
        sa.Column("audio_path", sa.Text()),
        sa.Column("audio_sha256", sa.Text()),
        sa.Column("duration_s", sa.Numeric()),
        sa.Column("status", sa.Text(), nullable=False, server_default="ingested"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(_in("status", EPISODE_STATUSES), name="episodes_status_check"),
    )
    op.create_index("ix_episodes_status", "episodes", ["status"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("episodes.id", ondelete="CASCADE")),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("params", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("log", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(_in("kind", JOB_KINDS), name="jobs_kind_check"),
        sa.CheckConstraint(_in("status", JOB_STATUSES), name="jobs_status_check"),
    )
    # The worker's SKIP LOCKED claim orders by created_at within status='queued'.
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"])

    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text()),
        sa.Column("params", postgresql.JSONB()),
        sa.Column("hotwords_sha256", sa.Text()),
        sa.Column("raw_json_path", sa.Text(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("wer_vs_reference", sa.Numeric()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_transcripts_episode_id", "transcripts", ["episode_id"])
    # At most one current transcript per episode.
    op.create_index(
        "uq_transcripts_current_per_episode", "transcripts", ["episode_id"],
        unique=True, postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "words",
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transcripts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("i", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_s", sa.Numeric(), nullable=False),
        sa.Column("end_s", sa.Numeric()),
        sa.Column("conf", sa.Numeric()),
        sa.Column("speaker", sa.Integer(), nullable=False, server_default="-1"),
    )
    op.create_index("ix_words_transcript_start", "words", ["transcript_id", "start_s"])
    # Corpus search (PLAN §8, §11 T6). 'simple' — no stemming: a stemmer would erase the
    # morphology this corpus exists to study.
    op.execute(
        "CREATE INDEX ix_words_tsv ON words "
        "USING gin (to_tsvector('simple', text));"
    )

    op.create_table(
        "utterances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("i", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("start_s", sa.Numeric(), nullable=False),
        sa.Column("end_s", sa.Numeric(), nullable=False),
        sa.Column("text_asr", sa.Text(), nullable=False),
        sa.Column("text_verified", sa.Text()),
        sa.Column("verified_by", sa.String(128)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("flags", postgresql.ARRAY(sa.Text()), nullable=False,
                  server_default=sa.text("'{}'")),
        sa.UniqueConstraint("transcript_id", "i", name="uq_utterances_transcript_i"),
    )
    op.create_index(
        "ix_utterances_transcript_start", "utterances", ["transcript_id", "start_s"]
    )

    op.create_table(
        "utterance_edits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("utterance_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("utterances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("before", sa.Text()),
        sa.Column("after", sa.Text()),
        sa.Column("editor", sa.String(128)),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_utterance_edits_utterance_id", "utterance_edits", ["utterance_id"])

    op.create_table(
        "speakers",
        sa.Column("episode_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cluster", sa.Integer(), primary_key=True),
        sa.Column("label", sa.Text()),
    )

    op.create_table(
        "hotwords",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("term", sa.Text(), nullable=False, unique=True),
        sa.Column("weight", sa.Numeric(), nullable=False, server_default="1.0"),
        sa.Column("note", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
    )

    seed_hotwords()


def seed_hotwords() -> None:
    """Insert the §8 seed terms. Idempotent — never clobbers an operator's edits."""
    hotwords = sa.table(
        "hotwords",
        sa.column("term", sa.Text),
        sa.column("weight", sa.Numeric),
        sa.column("note", sa.Text),
        sa.column("active", sa.Boolean),
    )
    stmt = pg_insert(hotwords).values([
        {"term": term, "weight": weight, "note": note, "active": True}
        for term, weight, note in HOTWORD_SEED
    ])
    op.execute(stmt.on_conflict_do_nothing(index_elements=["term"]))


def downgrade() -> None:
    for table in (
        "settings", "hotwords", "speakers", "utterance_edits", "utterances",
        "words", "transcripts", "jobs", "episodes",
    ):
        op.drop_table(table)
