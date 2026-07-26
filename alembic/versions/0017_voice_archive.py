"""add encrypted opt-in voice archive

Revision ID: 0017_voice_archive
Revises: 0016_oauth_credentials
Create Date: 2026-07-13
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0017_voice_archive"
down_revision = "0016_oauth_credentials"
branch_labels = None
depends_on = None

RLS_TABLES = ["voice_assets"]
APP_ROLE_TABLES = ["voice_assets"]
APP_ROLE_ENV = "THOUGHTPINS_APP_DB_ROLE"
VOICE_TABLE = "voice_assets"
VOICE_COLUMNS = {
    "id",
    "user_id",
    "raw_entry_id",
    "storage_ref",
    "original_filename",
    "media_type",
    "container",
    "byte_size_original",
    "byte_size_encrypted",
    "storage_codec",
    "content_fingerprint",
    "transcript_chars",
    "transcription_language",
    "transcription_mode",
    "consent_version",
    "retention_purpose",
    "derived_data_status",
    "created_at_utc",
}
VOICE_INDEXES = {
    "ix_voice_assets_content_fingerprint": ["content_fingerprint"],
    "ix_voice_assets_raw_entry_id": ["raw_entry_id"],
    "ix_voice_assets_user_id": ["user_id"],
    "ix_voice_assets_user_created": ["user_id", "created_at_utc"],
    "ix_voice_assets_user_entry": ["user_id", "raw_entry_id"],
}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _has_table() -> bool:
    return VOICE_TABLE in sa.inspect(op.get_bind()).get_table_names()


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(VOICE_TABLE)}


def _indexes() -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(VOICE_TABLE)}


def _app_role() -> str:
    role = os.getenv(APP_ROLE_ENV, "").strip()
    if not role:
        return ""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"{APP_ROLE_ENV} must be a simple PostgreSQL role name")
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
    if not _has_table():
        op.create_table(
            VOICE_TABLE,
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("raw_entry_id", sa.String(length=32), nullable=True),
            sa.Column("storage_ref", sa.String(length=255), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("media_type", sa.String(length=128), nullable=True),
            sa.Column("container", sa.String(length=24), nullable=True),
            sa.Column("byte_size_original", sa.Integer(), nullable=False),
            sa.Column("byte_size_encrypted", sa.Integer(), nullable=False),
            sa.Column("storage_codec", sa.String(length=32), nullable=False),
            sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("transcript_chars", sa.Integer(), nullable=False),
            sa.Column("transcription_language", sa.String(length=16), nullable=True),
            sa.Column("transcription_mode", sa.String(length=16), nullable=False),
            sa.Column("consent_version", sa.String(length=32), nullable=False),
            sa.Column("retention_purpose", sa.String(length=64), nullable=False),
            sa.Column("derived_data_status", sa.String(length=24), nullable=False),
            sa.Column("created_at_utc", sa.DateTime(), nullable=False),
            sa.CheckConstraint("byte_size_original >= 0", name="ck_voice_assets_original_size"),
            sa.CheckConstraint("byte_size_encrypted >= 0", name="ck_voice_assets_encrypted_size"),
            sa.ForeignKeyConstraint(["raw_entry_id"], ["raw_entries.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("storage_ref"),
        )
    else:
        missing = VOICE_COLUMNS - _columns()
        if missing:
            raise RuntimeError(f"Existing {VOICE_TABLE} table is incomplete: missing {sorted(missing)}")

    existing_indexes = _indexes()
    for index_name, columns in VOICE_INDEXES.items():
        if index_name not in existing_indexes:
            op.create_index(index_name, VOICE_TABLE, columns, unique=False)

    if _is_postgres():
        tenant_expr = "NULLIF(current_setting('app.current_user_id', true), '')"
        op.execute("ALTER TABLE voice_assets ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE voice_assets FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON voice_assets")
        op.execute(
            f"""
            CREATE POLICY thoughtpins_tenant_isolation ON voice_assets
            USING (user_id = {tenant_expr})
            WITH CHECK (user_id = {tenant_expr})
            """
        )
        _grant_app_role_tables()


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON voice_assets")
        op.execute("ALTER TABLE voice_assets DISABLE ROW LEVEL SECURITY")
    if _has_table():
        existing_indexes = _indexes()
        for index_name in reversed(VOICE_INDEXES):
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=VOICE_TABLE)
        op.drop_table(VOICE_TABLE)
