"""add short sign-in code alongside the magic link

Revision ID: 0022_magic_link_code
Revises: 0021_magic_link_tokens
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022_magic_link_code"
down_revision = "0021_magic_link_tokens"
branch_labels = None
depends_on = None

TABLE = "magic_link_tokens"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE)}
    if "code_hash" not in columns:
        # Nullable: rows issued before this migration have no code.
        op.add_column(TABLE, sa.Column("code_hash", sa.String(length=128), nullable=True))
    if "code_attempts" not in columns:
        op.add_column(TABLE, sa.Column("code_attempts", sa.Integer(), nullable=False, server_default="0"))

    existing_indexes = {index["name"] for index in inspector.get_indexes(TABLE)}
    if "ix_magic_link_tokens_code_hash" not in existing_indexes:
        op.create_index("ix_magic_link_tokens_code_hash", TABLE, ["code_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_magic_link_tokens_code_hash", table_name=TABLE)
    op.drop_column(TABLE, "code_attempts")
    op.drop_column(TABLE, "code_hash")
