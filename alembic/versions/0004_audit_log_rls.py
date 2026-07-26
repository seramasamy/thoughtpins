"""add audit log row-level security

Revision ID: 0004_audit_log_rls
Revises: 0003_user_id_not_null
Create Date: 2026-05-22
"""

from alembic import op

revision = "0004_audit_log_rls"
down_revision = "0003_user_id_not_null"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    tenant_expr = "NULLIF(current_setting('app.current_user_id', true), '')"
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON audit_logs")
    op.execute(
        f"""
        CREATE POLICY thoughtpins_tenant_isolation ON audit_logs
        USING (user_id = {tenant_expr})
        WITH CHECK (user_id = {tenant_expr})
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON audit_logs")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")
