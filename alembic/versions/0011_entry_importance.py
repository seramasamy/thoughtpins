"""add explicit entry importance

Revision ID: 0011_entry_importance
Revises: 0010_safety_reports
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_entry_importance"
down_revision = "0010_safety_reports"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if "raw_entries" not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns("raw_entries")}


def _indexes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if "raw_entries" not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes("raw_entries")}


def _checks() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if "raw_entries" not in inspector.get_table_names():
        return set()
    return {constraint.get("name") for constraint in inspector.get_check_constraints("raw_entries")}


def upgrade() -> None:
    columns = _columns()
    with op.batch_alter_table("raw_entries") as batch:
        if "user_importance" not in columns:
            batch.add_column(sa.Column("user_importance", sa.Integer(), nullable=True))
        if "importance_source" not in columns:
            batch.add_column(sa.Column("importance_source", sa.String(length=32), nullable=True))
        if "importance_updated_at" not in columns:
            batch.add_column(sa.Column("importance_updated_at", sa.DateTime(), nullable=True))
        if "ck_raw_entries_user_importance_range" not in _checks():
            batch.create_check_constraint(
                "ck_raw_entries_user_importance_range",
                "user_importance IS NULL OR (user_importance >= 1 AND user_importance <= 5)",
            )
    if "ix_raw_entries_user_importance_date" not in _indexes():
        op.create_index(
            "ix_raw_entries_user_importance_date",
            "raw_entries",
            ["user_id", "user_importance", "local_date"],
        )


def downgrade() -> None:
    if "ix_raw_entries_user_importance_date" in _indexes():
        op.drop_index("ix_raw_entries_user_importance_date", table_name="raw_entries")
    columns = _columns()
    with op.batch_alter_table("raw_entries") as batch:
        if "ck_raw_entries_user_importance_range" in _checks():
            batch.drop_constraint("ck_raw_entries_user_importance_range", type_="check")
        if "importance_updated_at" in columns:
            batch.drop_column("importance_updated_at")
        if "importance_source" in columns:
            batch.drop_column("importance_source")
        if "user_importance" in columns:
            batch.drop_column("user_importance")
