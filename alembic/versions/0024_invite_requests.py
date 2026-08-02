"""add the private-launch invite request queue

Revision ID: 0024_invite_requests
Revises: 0023_invite_codes
Create Date: 2026-08-01
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0024_invite_requests"
down_revision = "0023_invite_codes"
branch_labels = None
depends_on = None

TABLE = "invite_requests"
POLICY = "thoughtpins_tenant_isolation"
# Declared as a literal so static RLS coverage can see it: the SQL below
# interpolates TABLE, which a source scan cannot resolve.
RLS_TABLES = ["invite_requests"]
APP_ROLE_TABLES = ["invite_requests"]
REQUIRED_COLUMNS = {
    "id",
    "user_id",
    "note",
    "status",
    "created_at_utc",
    "updated_at_utc",
    "notified_at_utc",
}
INDEXES = {
    "ix_invite_requests_user_id": ["user_id"],
    "ix_invite_requests_status": ["status"],
    "ix_invite_requests_notified": ["notified_at_utc"],
    "ix_invite_requests_user_status": ["user_id", "status"],
    "ix_invite_requests_status_created": ["status", "created_at_utc"],
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
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("note", sa.String(length=1000), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("created_at_utc", sa.DateTime(), nullable=False),
            sa.Column("updated_at_utc", sa.DateTime(), nullable=False),
            sa.Column("notified_at_utc", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
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
    tenant = "NULLIF(current_setting('app.current_user_id', true), '')"
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE}")
    op.execute(
        f"CREATE POLICY {POLICY} ON {TABLE} USING (user_id = {tenant}) WITH CHECK (user_id = {tenant})",
    )
    _grant_app_role_tables()


def downgrade() -> None:
    if _is_postgres():
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE}")
        op.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_table(TABLE)
