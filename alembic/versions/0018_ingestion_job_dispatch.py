"""track durable ingestion queue handoffs

Revision ID: 0018_ingestion_job_dispatch
Revises: 0017_voice_archive
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018_ingestion_job_dispatch"
down_revision = "0017_voice_archive"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_ingestion_jobs_user_dispatch"


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("ingestion_jobs")}


def _indexes() -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("ingestion_jobs")}


def upgrade() -> None:
    if "queued_at_utc" not in _columns():
        with op.batch_alter_table("ingestion_jobs") as batch:
            batch.add_column(sa.Column("queued_at_utc", sa.DateTime(), nullable=True))
    if INDEX_NAME not in _indexes():
        op.create_index(
            INDEX_NAME,
            "ingestion_jobs",
            ["user_id", "status", "queued_at_utc"],
            unique=False,
        )


def downgrade() -> None:
    if INDEX_NAME in _indexes():
        op.drop_index(INDEX_NAME, table_name="ingestion_jobs")
    if "queued_at_utc" in _columns():
        with op.batch_alter_table("ingestion_jobs") as batch:
            batch.drop_column("queued_at_utc")
