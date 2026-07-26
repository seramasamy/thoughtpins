"""add document library memory tables

Revision ID: 0006_document_library
Revises: 0005_app_devices
Create Date: 2026-05-25
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_document_library"
down_revision = "0005_app_devices"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    tenant_expr = "NULLIF(current_setting('app.current_user_id', true), '')"
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON {table_name}")
    op.execute(
        f"""
        CREATE POLICY thoughtpins_tenant_isolation ON {table_name}
        USING (user_id = {tenant_expr})
        WITH CHECK (user_id = {tenant_expr})
        """
    )


def upgrade() -> None:
    if not _has_table("document_sources"):
        op.create_table(
            "document_sources",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("raw_entry_id", sa.String(length=32), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=512), nullable=False),
            sa.Column("author", sa.String(length=255), nullable=True),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.Column("canonical_url", sa.Text(), nullable=True),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("processing_error", sa.Text(), nullable=True),
            sa.Column("sensitivity", sa.String(length=64), nullable=True),
            sa.Column("created_at_utc", sa.DateTime(), nullable=True),
            sa.Column("local_date", sa.Date(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["raw_entry_id"], ["raw_entries.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_document_sources_user_id", "document_sources", ["user_id"])
        op.create_index("ix_document_sources_raw_entry_id", "document_sources", ["raw_entry_id"])
        op.create_index("ix_document_sources_content_hash", "document_sources", ["content_hash"])
        op.create_index("ix_document_sources_created_at_utc", "document_sources", ["created_at_utc"])
        op.create_index("ix_document_sources_local_date", "document_sources", ["local_date"])
        op.create_index("ix_document_sources_status", "document_sources", ["status"])
        op.create_index("ix_document_sources_user_created", "document_sources", ["user_id", "created_at_utc"])
        op.create_index("ix_document_sources_user_status", "document_sources", ["user_id", "status"])
        op.create_index("ix_document_sources_user_hash", "document_sources", ["user_id", "content_hash"])

    if not _has_table("document_chunks"):
        op.create_table(
            "document_chunks",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("document_id", sa.String(length=32), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("char_start", sa.Integer(), nullable=True),
            sa.Column("char_end", sa.Integer(), nullable=True),
            sa.Column("created_at_utc", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["document_sources.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])
        op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
        op.create_index("ix_document_chunks_user_document", "document_chunks", ["user_id", "document_id"])

    if _is_postgres():
        _enable_rls("document_sources")
        _enable_rls("document_chunks")


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON document_chunks")
        op.execute("ALTER TABLE document_chunks DISABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON document_sources")
        op.execute("ALTER TABLE document_sources DISABLE ROW LEVEL SECURITY")
    if _has_table("document_chunks"):
        op.drop_table("document_chunks")
    if _has_table("document_sources"):
        op.drop_table("document_sources")
