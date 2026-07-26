"""postgres row-level security policies

Revision ID: 0002_postgres_rls_policies
Revises: 0001_initial_schema
Create Date: 2026-05-22
"""

from alembic import op

revision = "0002_postgres_rls_policies"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

RLS_TABLES = [
    "ingestion_jobs",
    "raw_entries",
    "entities",
    "entity_mentions",
    "memories",
    "relationships",
    "events",
    "event_participants",
    "action_items",
    "expenses",
    "reports",
    "audit_logs",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    tenant_expr = "NULLIF(current_setting('app.current_user_id', true), '')"
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY thoughtpins_tenant_isolation ON {table}
            USING (user_id = {tenant_expr})
            WITH CHECK (user_id = {tenant_expr})
            """
        )


def downgrade() -> None:
    if not _is_postgres():
        return

    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
