"""transcripts.speakers_pending — the ASR-only transcript shown while diarization runs.

The worker now publishes the ASR text as soon as ASR finishes (~25–70 s) instead of
after diarization (~3–5 min). That preliminary run is its own raw JSON and its own
transcript row (PLAN §0.2); this flag marks it so the API can say "speakers pending"
and refuse edits against utterance boundaries that are about to be replaced.

Additive: existing rows are finished transcripts, so the default is false.

Revision ID: 0003_speakers_pending
Revises: 0002_hotwords_model_form
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_speakers_pending"
down_revision = "0002_hotwords_model_form"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcripts",
        sa.Column("speakers_pending", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("transcripts", "speakers_pending")
