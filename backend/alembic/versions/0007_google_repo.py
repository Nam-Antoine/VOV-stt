"""google repo — state for the Google Sheet + Docs repository (GOOGLE_REPO_PLAN Task 3).

Additive only:

``google_repo_state``   key/value: ``folder_id``, ``sheet_id``, ``last_full_sync``.
``episode_google_doc``  one row per episode Doc. ``episode_id`` is set to NULL, not
                        cascaded, when an episode is deleted: the Doc stays in Drive
                        (code never deletes there), and the row is how ``--status``
                        reports it as an orphan.

Downgrade drops exactly these two tables.

Revision ID: 0007_google_repo
Revises: 0006_drop_speakers
Create Date: 2026-09-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_google_repo"
down_revision = "0006_drop_speakers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_repo_state",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_table(
        "episode_google_doc",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("episodes.id", ondelete="SET NULL"), unique=True),
        sa.Column("doc_id", sa.Text()),
        sa.Column("text_sha256", sa.Text()),
        sa.Column("layer_used", sa.Text()),
        sa.Column("doc_title", sa.Text()),
        sa.Column("syllables", sa.Integer()),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("episode_google_doc")
    op.drop_table("google_repo_state")
