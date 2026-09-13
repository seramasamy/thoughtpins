"""Store encrypted originals and resumable imports in the shared database.

Revision ID: 0027_vault_import_chunks
Revises: 0026_chat_message_supersede

Both tables enforce tenant ownership with PostgreSQL RLS and application-role
grants. Original attachments are durable; import chunks are temporary. Downgrade
refuses to discard either: migrate and verify originals in replacement storage,
then remove those rows, and cancel or expire staged transfers before rolling
back. A backup alone does not make destructive downgrade safe. Existing staged
filesystem imports are adopted by the API when they resume or request preview;
legacy originals require the separate, ownership-checked maintenance migration.
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0027_vault_import_chunks"
down_revision = "0026_chat_message_supersede"
branch_labels = None
depends_on = None
TABLE = "vault_import_chunks"
RLS_TABLES = ["vault_import_chunks", "stored_attachments"]
APP_ROLE_TABLES = ["vault_import_chunks", "stored_attachments"]


def upgrade() -> None:
    bind = op.get_bind()
    if "stored_attachments" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "stored_attachments",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reference", sa.String(255), nullable=False, unique=True),
            sa.Column("original_filename", sa.String(100), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("payload", sa.LargeBinary(), nullable=False),
            sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        )
    if "ix_stored_attachments_user_id" not in {i["name"] for i in sa.inspect(bind).get_indexes("stored_attachments")}:
        op.create_index("ix_stored_attachments_user_id", "stored_attachments", ["user_id"])
    if TABLE not in sa.inspect(bind).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "transfer_id",
                sa.String(32),
                sa.ForeignKey("vault_import_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("offset", sa.Integer(), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("payload", sa.LargeBinary(), nullable=False),
        )
    if "ix_vault_import_chunks_owner_offset" not in {i["name"] for i in sa.inspect(bind).get_indexes(TABLE)}:
        op.create_index("ix_vault_import_chunks_owner_offset", TABLE, ["user_id", "transfer_id", "offset"], unique=True)
    if bind.dialect.name != "postgresql":
        return
    tenant = "NULLIF(current_setting('app.current_user_id', true), '')"
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY thoughtpins_tenant_isolation ON {table} USING (user_id = {tenant}) WITH CHECK (user_id = {tenant})"
        )
    role = os.getenv("THOUGHTPINS_APP_DB_ROLE", "").strip()
    if role:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
            raise ValueError("Invalid application database role")
        for table in APP_ROLE_TABLES:
            op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO "{role}"')


def downgrade() -> None:
    for table in RLS_TABLES:
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("Migrate original attachments and cancel staged vault transfers before downgrading")
    op.drop_table(TABLE)
    op.drop_table("stored_attachments")
