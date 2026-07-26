"""add article ingestion provenance fields

Revision ID: 0007_article_provenance_fields
Revises: 0006_document_library
Create Date: 2026-05-30
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_article_provenance_fields"
down_revision = "0006_document_library"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    _add_column_if_missing("document_sources", sa.Column("original_url", sa.Text(), nullable=True))
    _add_column_if_missing("document_sources", sa.Column("source_domain", sa.String(length=255), nullable=True))
    _add_column_if_missing("document_sources", sa.Column("access_method", sa.String(length=32), nullable=True))
    _add_column_if_missing("document_sources", sa.Column("rights_basis", sa.String(length=32), nullable=True))
    _add_column_if_missing("document_sources", sa.Column("fetch_status", sa.String(length=32), nullable=True))
    _add_column_if_missing("document_sources", sa.Column("paywall_detected", sa.Boolean(), nullable=True))
    _add_column_if_missing("document_sources", sa.Column("retrieval_quality_score", sa.Float(), nullable=True))
    _add_column_if_missing("document_sources", sa.Column("published_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("document_chunks", sa.Column("token_count", sa.Integer(), nullable=True))
    _add_column_if_missing("document_chunks", sa.Column("embedding_id", sa.String(length=128), nullable=True))
    _add_column_if_missing("document_chunks", sa.Column("section_heading", sa.String(length=255), nullable=True))

    if _has_table("document_sources") and not _has_index("document_sources", "ix_document_sources_user_domain"):
        op.create_index(
            "ix_document_sources_user_domain",
            "document_sources",
            ["user_id", "source_domain"],
        )


def downgrade() -> None:
    if _has_table("document_sources") and _has_index("document_sources", "ix_document_sources_user_domain"):
        op.drop_index("ix_document_sources_user_domain", table_name="document_sources")
    # Keep downgrade conservative for SQLite compatibility. The added columns are
    # nullable metadata fields and do not affect existing source data.
