"""add private-launch invite codes and per-account admission

Revision ID: 0023_invite_codes
Revises: 0022_magic_link_code
Create Date: 2026-08-01
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0023_invite_codes"
down_revision = "0022_magic_link_code"
branch_labels = None
depends_on = None

TABLE = "invite_codes"
# No RLS policy here by design, matching magic_link_tokens: a code is issued by
# an operator before anyone redeems it and may admit several accounts, so there
# is no owning tenant to scope rows to. The table holds a hashed code, a label,
# and counters — never journal content. Which account redeemed a code is
# recorded on users, which is tenant scoped.
APP_ROLE_TABLES = ["invite_codes"]
REQUIRED_COLUMNS = {
    "id",
    "code_hash",
    "label",
    "max_uses",
    "used_count",
    "created_at_utc",
    "expires_at_utc",
    "revoked_at_utc",
}
USER_COLUMNS = {
    "invite_code_id": sa.Column("invite_code_id", sa.String(length=32), nullable=True),
    "invite_redeemed_at_utc": sa.Column("invite_redeemed_at_utc", sa.DateTime(), nullable=True),
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
            sa.Column("code_hash", sa.String(length=128), nullable=False),
            sa.Column("label", sa.String(length=128), nullable=True),
            sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at_utc", sa.DateTime(), nullable=False),
            sa.Column("expires_at_utc", sa.DateTime(), nullable=True),
            sa.Column("revoked_at_utc", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code_hash"),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns(TABLE)}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"Existing {TABLE} table is incomplete: missing {sorted(missing)}")

    inspector = sa.inspect(op.get_bind())
    existing_indexes = {index["name"] for index in inspector.get_indexes(TABLE)}
    if "ix_invite_codes_code_hash" not in existing_indexes:
        op.create_index("ix_invite_codes_code_hash", TABLE, ["code_hash"], unique=True)
    if "ix_invite_codes_expires" not in existing_indexes:
        op.create_index("ix_invite_codes_expires", TABLE, ["expires_at_utc"], unique=False)

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    for name, column in USER_COLUMNS.items():
        if name not in user_columns:
            op.add_column("users", column)
    user_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("users")}
    if "ix_users_invite_code_id" not in user_indexes:
        op.create_index("ix_users_invite_code_id", "users", ["invite_code_id"], unique=False)

    if not _is_postgres():
        return
    _grant_app_role_tables()


def downgrade() -> None:
    op.drop_index("ix_users_invite_code_id", table_name="users")
    for name in USER_COLUMNS:
        op.drop_column("users", name)
    op.drop_table(TABLE)
