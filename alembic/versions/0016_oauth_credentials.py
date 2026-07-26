"""add durable OAuth identity credentials

Revision ID: 0016_oauth_credentials
Revises: 0015_ingestion_job_dedup
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_oauth_credentials"
down_revision = "0015_ingestion_job_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "oauth_credentials" in inspector.get_table_names():
        return
    op.create_table(
        "oauth_credentials",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_subject_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), nullable=False),
        sa.Column("last_used_at_utc", sa.DateTime(), nullable=False),
        sa.Column("revoked_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oauth_credentials_user_id", "oauth_credentials", ["user_id"], unique=False)
    op.create_index(
        "ix_oauth_credentials_provider_subject",
        "oauth_credentials",
        ["provider", "provider_subject_hash"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_credentials_user_provider",
        "oauth_credentials",
        ["user_id", "provider"],
        unique=True,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "oauth_credentials" not in inspector.get_table_names():
        return
    op.drop_index("ix_oauth_credentials_user_provider", table_name="oauth_credentials")
    op.drop_index("ix_oauth_credentials_provider_subject", table_name="oauth_credentials")
    op.drop_index("ix_oauth_credentials_user_id", table_name="oauth_credentials")
    op.drop_table("oauth_credentials")
