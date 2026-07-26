"""add metered LLM usage events

Revision ID: 0020_llm_usage_events
Revises: 0019_vault_import_sessions
Create Date: 2026-07-26
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0020_llm_usage_events"
down_revision = "0019_vault_import_sessions"
branch_labels = None
depends_on = None

TABLE = "llm_usage_events"
POLICY = "thoughtpins_tenant_isolation"
RLS_TABLES = ["llm_usage_events"]
APP_ROLE_TABLES = ["llm_usage_events"]
REQUIRED_COLUMNS = {
    "id",
    "user_id",
    "created_at_utc",
    "provider",
    "model",
    "operation",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "request_id",
}
INDEXES = {
    "ix_llm_usage_events_user_id": ["user_id"],
    "ix_llm_usage_events_user_created": ["user_id", "created_at_utc"],
    "ix_llm_usage_events_created": ["created_at_utc"],
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
            sa.Column("created_at_utc", sa.DateTime(), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=False),
            sa.Column("operation", sa.String(length=32), nullable=False),
            sa.Column("prompt_tokens", sa.Integer(), nullable=False),
            sa.Column("completion_tokens", sa.Integer(), nullable=False),
            sa.Column("total_tokens", sa.Integer(), nullable=False),
            sa.Column("cost_usd", sa.Float(), nullable=False),
            sa.Column("request_id", sa.String(length=64), nullable=True),
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
