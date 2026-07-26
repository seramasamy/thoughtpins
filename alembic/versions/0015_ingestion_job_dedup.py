"""add tenant-scoped ingestion job deduplication

Revision ID: 0015_ingestion_job_dedup
Revises: 0014_api_idempotency
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_ingestion_job_dedup"
down_revision = "0014_api_idempotency"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("ingestion_jobs")}


def upgrade() -> None:
    if "dedup_key" not in _columns():
        with op.batch_alter_table("ingestion_jobs") as batch:
            batch.add_column(sa.Column("dedup_key", sa.String(length=160), nullable=True))
            batch.create_index("ix_ingestion_jobs_user_dedup", ["user_id", "dedup_key"], unique=True)


def downgrade() -> None:
    if "dedup_key" in _columns():
        with op.batch_alter_table("ingestion_jobs") as batch:
            batch.drop_index("ix_ingestion_jobs_user_dedup")
            batch.drop_column("dedup_key")
