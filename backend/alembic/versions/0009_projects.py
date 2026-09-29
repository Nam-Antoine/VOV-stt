"""projects — every episode belongs to one, each with its own Drive folder + Sheet.

Backward-compatible: a single project "Đàn bà 30+" is created and takes over the
folder_id/sheet_id/sheet_sha256/last_full_sync that ``google_repo_state`` already holds
(copied, not moved — the old keys are left as-is so nothing about the running sync
breaks mid-deploy). Every existing episode and its Doc's folder are backfilled to it, so
the live Sheet keeps its URL and its rows.

Revision ID: 0009_projects
Revises: 0008_google_sync_jobs
Create Date: 2026-09-29
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_projects"
down_revision = "0008_google_sync_jobs"
branch_labels = None
depends_on = None

DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_SLUG = "dan-ba-30"
DEFAULT_NAME = "Đàn bà 30+"


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("google_folder_id", sa.Text()),
        sa.Column("google_sheet_id", sa.Text()),
        sa.Column("google_sheet_sha256", sa.Text()),
        #: The name last written to the Drive folder/Sheet titles; a rename is detected
        #: by comparing this to ``name`` (google_repo/docs.py, sheet.py).
        sa.Column("google_title", sa.Text()),
        sa.Column("google_last_full_sync", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    conn = op.get_bind()
    state = {row[0]: row[1] for row in conn.execute(
        sa.text("SELECT key, value FROM google_repo_state")
    )}
    conn.execute(
        sa.text(
            "INSERT INTO projects (id, slug, name, google_folder_id, google_sheet_id, "
            "google_sheet_sha256, google_title, google_last_full_sync) "
            "VALUES (:id, :slug, :name, :folder_id, :sheet_id, :sha256, :name, :last_sync)"
        ),
        {
            "id": uuid.UUID(DEFAULT_PROJECT_ID),
            "slug": DEFAULT_SLUG,
            "name": DEFAULT_NAME,
            "folder_id": state.get("folder_id"),
            "sheet_id": state.get("sheet_id"),
            "sha256": state.get("sheet_sha256"),
            "last_sync": state.get("last_full_sync"),
        },
    )

    op.add_column(
        "episodes",
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="RESTRICT")),
    )
    conn.execute(sa.text(
        "UPDATE episodes SET project_id = :id"
    ), {"id": uuid.UUID(DEFAULT_PROJECT_ID)})
    op.alter_column("episodes", "project_id", nullable=False)
    op.create_index("ix_episodes_project_id", "episodes", ["project_id"])

    # So a Doc whose episode moves to another project also moves in Drive
    # (google_repo/docs.py compares this to the project's current folder).
    op.add_column("episode_google_doc", sa.Column("folder_id", sa.Text()))
    if state.get("folder_id"):
        conn.execute(sa.text(
            "UPDATE episode_google_doc SET folder_id = :folder_id WHERE doc_id IS NOT NULL"
        ), {"folder_id": state["folder_id"]})


def downgrade() -> None:
    op.drop_column("episode_google_doc", "folder_id")
    op.drop_index("ix_episodes_project_id", table_name="episodes")
    op.drop_column("episodes", "project_id")
    op.drop_table("projects")
