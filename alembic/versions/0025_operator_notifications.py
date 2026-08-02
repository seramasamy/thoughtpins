"""record operator notifications so send throttles need no tenant walk

Revision ID: 0025_operator_notifications
Revises: 0024_invite_requests
Create Date: 2026-08-02
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0025_operator_notifications"
down_revision = "0024_invite_requests"
branch_labels = None
depends_on = None

TABLE = "operator_notifications"
# No RLS by design, like invite_codes: a row says the person running the service
# was emailed, which belongs to no tenant. It holds a kind, a timestamp, and a
# count — never journal content and never an address.
APP_ROLE_TABLES = ["operator_notifications"]
REQUIRED_COLUMNS = {"id", "kind", "sent_at_utc", "item_count"}
INDEXES = {"ix_operator_notifications_kind_sent": ["kind", "sent_at_utc"]}


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
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("sent_at_utc", sa.DateTime(), nullable=False),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
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
    _grant_app_role_tables()


def downgrade() -> None:
    op.drop_table(TABLE)
