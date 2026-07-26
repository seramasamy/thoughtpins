"""add resumable Obsidian vault import sessions

Revision ID: 0019_vault_import_sessions
Revises: 0018_ingestion_job_dispatch
Create Date: 2026-07-19
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0019_vault_import_sessions"
down_revision = "0018_ingestion_job_dispatch"
branch_labels = None
depends_on = None

TABLE = "vault_import_sessions"
POLICY = "thoughtpins_tenant_isolation"
RLS_TABLES = ["vault_import_sessions"]
APP_ROLE_TABLES = ["vault_import_sessions"]
REQUIRED_COLUMNS = {
    "id",
    "user_id",
    "status",
    "operation",
    "filename",
    "mode",
    "conflict_policy",
    "expected_bytes",
    "received_bytes",
    "archive_sha256",
    "verified_sha256",
    "storage_key",
    "progress_current",
    "progress_total",
    "progress_stage",
    "cancel_requested",
    "result_json",
    "error",
    "created_at_utc",
    "updated_at_utc",
    "started_at_utc",
    "finished_at_utc",
    "expires_at_utc",
}
INDEXES = {
    "ix_vault_import_sessions_user_id": ["user_id"],
    "ix_vault_import_sessions_status": ["status"],
    "ix_vault_import_sessions_expires": ["expires_at_utc"],
    "ix_vault_import_sessions_user_status": ["user_id", "status"],
    "ix_vault_import_sessions_user_created": ["user_id", "created_at_utc"],
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
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("operation", sa.String(length=16), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("conflict_policy", sa.String(length=16), nullable=False),
            sa.Column("expected_bytes", sa.Integer(), nullable=False),
            sa.Column("received_bytes", sa.Integer(), nullable=False),
            sa.Column("archive_sha256", sa.String(length=64), nullable=True),
            sa.Column("verified_sha256", sa.String(length=64), nullable=True),
            sa.Column("storage_key", sa.String(length=64), nullable=False),
            sa.Column("progress_current", sa.Integer(), nullable=False),
            sa.Column("progress_total", sa.Integer(), nullable=False),
            sa.Column("progress_stage", sa.String(length=32), nullable=False),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at_utc", sa.DateTime(), nullable=False),
            sa.Column("updated_at_utc", sa.DateTime(), nullable=False),
            sa.Column("started_at_utc", sa.DateTime(), nullable=True),
            sa.Column("finished_at_utc", sa.DateTime(), nullable=True),
            sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("storage_key"),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns(TABLE)}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"Existing {TABLE} table is incomplete: missing {sorted(missing)}")
        unique_columns = {
            tuple(constraint.get("column_names") or []) for constraint in inspector.get_unique_constraints(TABLE)
        }
        if ("storage_key",) not in unique_columns:
            raise RuntimeError(f"Existing {TABLE} table must keep storage_key unique")

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
