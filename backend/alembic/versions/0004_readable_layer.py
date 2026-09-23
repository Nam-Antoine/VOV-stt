"""utterances.text_readable / readable_from — the punctuated, cased reading layer.

A derived layer computed by ViBERT-capu (app/readable.py) for people who read the
programme rather than study the speech. The corpus columns (text_asr, text_verified) are
untouched (CLAUDE.md rule 1). readable_from records the text the readable version was
computed from, so an edit or split marks it stale instead of silently disagreeing.

Additive and nullable: NULL means "not computed yet".

Revision ID: 0004_readable_layer
Revises: 0003_speakers_pending
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_readable_layer"
down_revision = "0003_speakers_pending"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("utterances", sa.Column("text_readable", sa.Text(), nullable=True))
    op.add_column("utterances", sa.Column("readable_from", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("utterances", "readable_from")
    op.drop_column("utterances", "text_readable")
