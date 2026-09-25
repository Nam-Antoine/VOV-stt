"""google_sync jobs — allow the new job kind (GOOGLE_REPO_PLAN Task 7).

Widens ``jobs_kind_check`` to include ``google_sync``. Additive: every existing row still
satisfies it. Downgrade removes any google_sync jobs (queue entries, not data) and
restores the old constraint.

Revision ID: 0008_google_sync_jobs
Revises: 0007_google_repo
Create Date: 2026-09-25
"""
from __future__ import annotations

from alembic import op

revision = "0008_google_sync_jobs"
down_revision = "0007_google_repo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("jobs_kind_check", "jobs", type_="check")
    op.create_check_constraint(
        "jobs_kind_check", "jobs", "kind in ('transcribe', 'export', 'google_sync')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind = 'google_sync'")
    op.drop_constraint("jobs_kind_check", "jobs", type_="check")
    op.create_check_constraint("jobs_kind_check", "jobs", "kind in ('transcribe', 'export')")
