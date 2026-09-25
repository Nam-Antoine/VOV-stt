"""drop speakers — diarization is removed; transcripts carry no speaker information.

Drops the ``speakers`` label table, ``words.speaker``, ``utterances.speaker`` and
``transcripts.speakers_pending``. The DB rows are a derived projection; the raw JSON
under /data/raw keeps whatever diarization an old run recorded (PLAN §0.2). At the time
of this migration every label in ``speakers`` was an automatic Host/Guest guess, none
typed by a person.

Downgrade restores the columns with their defaults (every speaker -1, no labels); the
old cluster numbers are not recovered.

Revision ID: 0006_drop_speakers
Revises: 0005_users
Create Date: 2026-09-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_drop_speakers"
down_revision = "0005_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("speakers")
    op.drop_column("words", "speaker")
    op.drop_column("utterances", "speaker")
    op.drop_column("transcripts", "speakers_pending")


def downgrade() -> None:
    op.add_column(
        "transcripts",
        sa.Column("speakers_pending", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )
    op.add_column(
        "utterances",
        sa.Column("speaker", sa.Integer(), nullable=False, server_default="-1"),
    )
    op.add_column(
        "words",
        sa.Column("speaker", sa.Integer(), nullable=False, server_default="-1"),
    )
    op.create_table(
        "speakers",
        sa.Column("episode_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cluster", sa.Integer(), primary_key=True),
        sa.Column("label", sa.Text()),
    )
