"""add tenant-scoped API idempotency records

Revision ID: 0014_api_idempotency
Revises: 0013_entity_salience_signals
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_api_idempotency"
down_revision = "0013_entity_salience_signals"
branch_labels = None
depends_on = None

RLS_TABLES = ["api_idempotency_records"]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "api_idempotency_records",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.Column("completed_at_utc", sa.DateTime(), nullable=True),
        sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_api_idempotency_user_scope_key",
        "api_idempotency_records",
        ["user_id", "scope", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_api_idempotency_user_expires",
        "api_idempotency_records",
        ["user_id", "expires_at_utc"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_idempotency_records_user_id"),
        "api_idempotency_records",
        ["user_id"],
        unique=False,
    )

    if _is_postgres():
        tenant_expr = "NULLIF(current_setting('app.current_user_id', true), '')"
        op.execute("ALTER TABLE api_idempotency_records ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON api_idempotency_records")
        op.execute(
            f"""
            CREATE POLICY thoughtpins_tenant_isolation ON api_idempotency_records
            USING (user_id = {tenant_expr})
            WITH CHECK (user_id = {tenant_expr})
            """
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON api_idempotency_records")
        op.execute("ALTER TABLE api_idempotency_records DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f("ix_api_idempotency_records_user_id"), table_name="api_idempotency_records")
    op.drop_index("ix_api_idempotency_user_expires", table_name="api_idempotency_records")
    op.drop_index("ix_api_idempotency_user_scope_key", table_name="api_idempotency_records")
    op.drop_table("api_idempotency_records")
