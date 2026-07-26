"""add safety reports

Revision ID: 0010_safety_reports
Revises: 0009_postgres_app_role_grants
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_safety_reports"
down_revision = "0009_postgres_app_role_grants"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _has_table(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return name in inspector.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_present(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _enable_rls(table_name: str) -> None:
    if not _is_postgres():
        return
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
    if not _has_table("safety_reports"):
        op.create_table(
            "safety_reports",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="app"),
            sa.Column("target_type", sa.String(length=64), nullable=True),
            sa.Column("target_id", sa.String(length=64), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
            sa.Column("created_at_utc", sa.DateTime(), nullable=True),
            sa.Column("reviewed_at_utc", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing("ix_safety_reports_user_id", "safety_reports", ["user_id"])
    _create_index_if_missing("ix_safety_reports_user_status", "safety_reports", ["user_id", "status"])
    _create_index_if_missing("ix_safety_reports_user_created", "safety_reports", ["user_id", "created_at_utc"])
    _create_index_if_missing("ix_safety_reports_category", "safety_reports", ["category"])
    _create_index_if_missing("ix_safety_reports_target_id", "safety_reports", ["target_id"])
    _enable_rls("safety_reports")


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON safety_reports")
        op.execute("ALTER TABLE safety_reports DISABLE ROW LEVEL SECURITY")
    _drop_index_if_present("ix_safety_reports_target_id", "safety_reports")
    _drop_index_if_present("ix_safety_reports_category", "safety_reports")
    _drop_index_if_present("ix_safety_reports_user_created", "safety_reports")
    _drop_index_if_present("ix_safety_reports_user_status", "safety_reports")
    _drop_index_if_present("ix_safety_reports_user_id", "safety_reports")
    if _has_table("safety_reports"):
        op.drop_table("safety_reports")
