"""add versioned contextual salience fields

Revision ID: 0012_contextual_salience
Revises: 0011_entry_importance
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_contextual_salience"
down_revision = "0011_entry_importance"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    raw_columns = _columns("raw_entries")
    with op.batch_alter_table("raw_entries") as batch:
        additions = {
            "analysis_json": sa.Column("analysis_json", sa.JSON(), nullable=True),
            "contextual_salience": sa.Column("contextual_salience", sa.Float(), nullable=True),
            "salience_uncertainty": sa.Column("salience_uncertainty", sa.Float(), nullable=True),
            "salience_model_version": sa.Column("salience_model_version", sa.String(length=32), nullable=True),
            "salience_updated_at": sa.Column("salience_updated_at", sa.DateTime(), nullable=True),
        }
        for name, column in additions.items():
            if name not in raw_columns:
                batch.add_column(column)

    entity_columns = _columns("entities")
    with op.batch_alter_table("entities") as batch:
        additions = {
            "salience_score": sa.Column("salience_score", sa.Float(), nullable=True),
            "salience_uncertainty": sa.Column("salience_uncertainty", sa.Float(), nullable=True),
            "salience_model_version": sa.Column("salience_model_version", sa.String(length=32), nullable=True),
            "salience_updated_at": sa.Column("salience_updated_at", sa.DateTime(), nullable=True),
        }
        for name, column in additions.items():
            if name not in entity_columns:
                batch.add_column(column)

    if "ix_entities_user_salience" not in _indexes("entities"):
        op.create_index(
            "ix_entities_user_salience",
            "entities",
            ["user_id", "salience_score", "updated_at_utc"],
        )


def downgrade() -> None:
    if "ix_entities_user_salience" in _indexes("entities"):
        op.drop_index("ix_entities_user_salience", table_name="entities")
    entity_columns = _columns("entities")
    with op.batch_alter_table("entities") as batch:
        for name in ("salience_updated_at", "salience_model_version", "salience_uncertainty", "salience_score"):
            if name in entity_columns:
                batch.drop_column(name)

    raw_columns = _columns("raw_entries")
    with op.batch_alter_table("raw_entries") as batch:
        for name in (
            "salience_updated_at",
            "salience_model_version",
            "salience_uncertainty",
            "contextual_salience",
            "analysis_json",
        ):
            if name in raw_columns:
                batch.drop_column(name)
