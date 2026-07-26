"""add passwordless magic-link sign-in tokens

Revision ID: 0021_magic_link_tokens
Revises: 0020_llm_usage_events
Create Date: 2026-07-26
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0021_magic_link_tokens"
down_revision = "0020_llm_usage_events"
branch_labels = None
depends_on = None

TABLE = "magic_link_tokens"
# No RLS policy here by design: rows are keyed by email and read before any
# tenant context exists (and may precede the account they create), matching the
# documented pre-authentication exemption for auth_sessions/oauth_credentials.
# The table holds only a hashed token and an email, never journal content.
APP_ROLE_TABLES = ["magic_link_tokens"]
REQUIRED_COLUMNS = {
    "id",
    "email",
    "token_hash",
    "created_at_utc",
    "expires_at_utc",
    "consumed_at_utc",
    "request_ip_hash",
}
INDEXES = {
    "ix_magic_link_tokens_email": ["email"],
    "ix_magic_link_tokens_email_created": ["email", "created_at_utc"],
    "ix_magic_link_tokens_expires": ["expires_at_utc"],
}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _app_role() -> str:
    role = os.getenv("THOUGHTPINS_APP_DB_ROLE", "").strip()
    if role and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError("THOUGHTPINS_APP_DB_ROLE must be a simple PostgreSQL role name")
    return role


def _grant_app_role_tables() -> None:
    role = _app_role()
    if not role:
        return
    bind = op.get_bind()
    exists = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}).scalar()
    if not exists:
        raise RuntimeError(f"Configured PostgreSQL application role {role!r} does not exist")
    quoted_role = f'"{role}"'
    for table in APP_ROLE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {quoted_role}")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("created_at_utc", sa.DateTime(), nullable=False),
            sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
            sa.Column("consumed_at_utc", sa.DateTime(), nullable=True),
            sa.Column("request_ip_hash", sa.String(length=64), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns(TABLE)}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"Existing {TABLE} table is incomplete: missing {sorted(missing)}")

    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    for name, columns in INDEXES.items():
        if name not in existing_indexes:
            op.create_index(name, TABLE, columns, unique=False)

    if not _is_postgres():
        return
    _grant_app_role_tables()


def downgrade() -> None:
    op.drop_table(TABLE)
